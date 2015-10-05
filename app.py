from flask import Flask, render_template, request, redirect
import bokeh as bk
from bokeh.charts import Histogram
from bokeh.plotting import figure, show,ColumnDataSource,gridplot
from bokeh.resources import CDN
from bokeh.io import output_notebook
import requests
from bs4 import BeautifulSoup
import re
import json
import requests
from bs4 import BeautifulSoup
import networkx
from requests_futures.sessions import FuturesSession
import pandas as pd
import numpy as np
from bokeh.models import HoverTool, Circle,TapTool, OpenURL
from bokeh.embed import components
import os
app = Flask(__name__)
app_vars={}
value_option={u'Close':4,u'Adj. Close':11,u'Volume':5}
colors=['blue','red','green']
widths=[1.5,1,1]

#functions
fs=FuturesSession(max_workers=20)
def get_rev(bs):
    reviewids=re.findall('"(revData[^"]+)"',str(bs))
    rev=u""
    for rid in reviewids:
        try:
            rev=rev+bs.select('div#'+reviewids[1])[0].select('div.a-section')[-1].text
        except:
            pass
    try:
        for black in bs.find_all(attrs={'data-action':'columnbalancing-showfullreview'}):
            rev=rev+json.loads(block['data-columnbalancing-showfullreview'])['rest']
    except:
        pass
    return rev

def get_rev_title(bs):
    poss_rev=bs.select('span.a-size-base.a-text-bold')
    rev_t=[]
    for i in range(1,4):
        try: 
            rev_t.append(poss_rev[i].text)
        except:
            pass
        
    return rev_t


def get_info(asin,fsession=fs):
    tryn=0
    while tryn<10:
        res=fs.get('http://www.amazon.com/o/ASIN/'+asin).result()
        if res.status_code==200: 
            break
        else: tryn=tryn+1
    if tryn<10:
        bs=BeautifulSoup(res.content)
        try:
            related=map(str,json.loads(re.search('"id_list":(\[[^\]]+\])',str(bs)).group(1)))
            score=float(re.search('"([0-9\.]+) out of 5 stars',str(bs)).group(1))
            review=int(re.search('([0-9]+) customer review',str(bs)).group(1))
            review_title=get_rev_title(bs)
            img_link=bs.select('div#imgTagWrapperId')[0].img['src']
        except:
            related=[]
            score=0
            review=0
            review_title=''
            img_link=''
        name=bs.select('span#productTitle')[0].get_text()
    else:
        name=''
        review=0
        score=0
        related=[]
        review_title=''
        img_link=''
    return asin, name, review, score, related, review_title,img_link


def get_result(asin,step=1,maxn=10):
    colors=['red',]+['yellow',]+['green',]
    asin, name, review, score, related,rev,img = get_info(asin)
    if len(related)>maxn:
        related=related[:maxn]
    df=pd.DataFrame(columns=['ASIN','Name','Number of reviews','Average rating','Review','IMG'])
    i=0
    df.loc[i]=[asin,name,review,score,rev,img]
    i=i+1
    G=networkx.DiGraph()
    for p in related:
        G.add_edge(asin,p)
    step_count=1
    current_list=related
    new_related=[]
    while step_count<=step:
        for a in current_list:
            asin1, name1, review1, score1, related1,rev1,img1 = get_info(a)
            df.loc[i]=[asin1,name1,review1,score1,rev1,img1]
            i=i+1
            new_related=new_related+[pa for pa in related1 if pa not in G.node.keys()]
            if step_count==step:
                for pa in related1:
                    if pa in G.node.keys():
                        G.add_edge(a,pa)
            else:
                for pa in related1:
                    G.add_edge(a,pa)
            if i>maxn:
                break
        step_count=step_count+1
        current_list=new_related[:]
        new_related=[]
    

    return df,G

def plot_net(df,G):
    colors=['red','yellow','green']
    
    central=networkx.in_degree_centrality(G)
    Ss=np.array(central.values())
    Ss=((Ss-min(Ss)+0.00001)/(max(Ss)-min(Ss)+0.00001)*0.045+0.005)*2/(len(G.nodes())**0.25)
    Sizes=dict(zip(central.keys(),Ss))
    pts = networkx.spring_layout(G)
    mi, ma=np.array(pts.values()).min()-0.1, np.array(pts.values()).max()+0.1
    def add_arrow(x1,x2,r=0.2):
        return [x2-(x2-x1)*r,x2]
    def change_nrev(nrev):
        if nrev<=1:
            return str(int(nrev))+' review'
        else:
            return str(int(nrev))+' reviews'
        
    nodes=sorted(G.nodes())
    df_s=df.sort('ASIN')
    source = ColumnDataSource(
        data=dict(
            x=[pts[node][0] for node in nodes],
            y=[pts[node][1] for node in nodes],
            ASIN=df_s.ASIN.tolist(),
            col=[colors[networkx.shortest_path_length(G,df.ASIN[0],node)] for node in nodes],
            siz=[Sizes[node] for node in nodes],
            rev=map(lambda r:'| '.join(map(str,r)),df_s.Review),
            img=df_s.IMG.tolist(),
            rating=map(lambda x: "{:.1f}".format(x) ,df_s['Average rating'].tolist()),
            nrev=map(change_nrev,df_s['Number of reviews'].tolist()),
            nrev_num=df_s['Number of reviews'].tolist(),
            rating_num=df_s['Average rating'].tolist(),
            name=df_s.Name,
            rd=[Sizes[node]*500 for node in nodes],
            outrd=[Sizes[node]*600 for node in nodes]
        )
    )
    
    mostrat=df[df['Average rating']==df['Average rating'].max()]['ASIN'].tolist()
    mostrev=df[df['Number of reviews']==df['Number of reviews'].max()]['ASIN'].tolist()
    TOOLS = 'pan,box_zoom,lasso_select,reset,,wheel_zoom,resize,help'
    p = figure(
        x_range = (mi,ma),
        y_range = (mi,ma),
        height= 600,
        width= 600,
        title="Network of related products",
        tools=TOOLS
    )

    for edge in G.edges():

        p.line( 
            x= [pts[pt][0] for pt in edge],
            y= [pts[pt][1] for pt in edge],
            line_cap='round',
            line_color='blue',
        )
        p.line( 
            x= add_arrow(*[pts[pt][0] for pt in edge]),
            y= add_arrow(*[pts[pt][1] for pt in edge]),
            line_cap='square',
            line_color='blue',
            line_width=5,
            line_alpha=0.5
        )

    circle=Circle(x='x',y='y',radius='siz',fill_color='col',fill_alpha=0.8,line_alpha=0.5)
    circle_renderer=p.add_glyph(source,circle)
    hover = HoverTool(tooltips="""
        <div>
            <div>
                <img
                    src="@img" height="60" alt="@img" width="60"
                    style="float: left; margin: 0px 15px 15px 0px;"
                    border="2"
                ></img>
            </div>
            <div style="width:250px">
                <span style="font-size: 12px; font-weight: bold;">@name (@ASIN)</span>
                <br />
                <span style="font-size:11.5px;"> Rating: @rating (@nrev) </span>
                <br />
                <span style="font-size: 11px; color: #966 ; width:150px;">@rev</span>
            </div>
        </div>
        """,renderers=[circle_renderer])
    p.add_tools(hover)
    
    url = 'http://www.amazon.com/o/ASIN/@ASIN'
    taptool = TapTool(action=OpenURL(url=url),renderers=[circle_renderer])
    # taptool has differnet attr name due to different version of bokeh.
    #    taptool = TapTool(callback=OpenURL(url=url),renderers=[circle_renderer])
    p.tools.append(taptool)
    p.annulus(
        x=[pts[node][0] for node in mostrat],
        y=[pts[node][1] for node in mostrat],
        inner_radius=[Sizes[node] for node in mostrat],
        outer_radius=[Sizes[node]*1.5 for node in mostrat],
        color='orange',alpha=0.8)
    
    p.annulus(
        x=[pts[node][0] for node in mostrev],
        y=[pts[node][1] for node in mostrev],
        inner_radius=[Sizes[node] for node in mostrev],
        outer_radius=[Sizes[node]*1.5 for node in mostrev],
        color='purple',alpha=0.8)
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None
    p.xaxis.major_label_text_color = None
    p.yaxis.major_label_text_color = None
    scatter=figure(
        x_range = (-df['Number of reviews'].max()*0.1,df['Number of reviews'].max()*1.1),
        y_range = (-0.5,5.5),
        height= 600,
        width= 500,
        title="Average rating and number of reviews",
        tools=TOOLS+",crosshair"
    )
    scatter.circle(x='nrev_num',y='rating_num',radius="rd",color='col',alpha=0.8,source=source)
    scatter.annulus(x='nrev_num',y='rating_num',inner_radius="rd",outer_radius='outrd',color='black',alpha=0.8,source=source)
    scatter.xaxis.axis_label = "Number of reviews"
    scatter.yaxis.axis_label = "Average rating"
    return gridplot([[p,scatter]])
    

@app.route('/')
def main():
    return redirect('/index')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/check_plot',methods=['GET','POST'])
def check_plot():
    if request.method=='POST':
        app_vars['ASIN']=request.form['ASIN'].strip()
        try:
            app_vars['maxn']=int(request.form['maxn'].strip())
        except:
            app_vars['maxn']=10
        if app_vars['maxn']<=0:
            app_vars['maxn']=10
            
    url='http://www.amazon.com/o/ASIN/'+app_vars['ASIN']
    testn=0
    test_page=requests.get(url)
    while testn<3 or test_page.status_code!=200:
        test_page=requests.get(url)
        testn+=1
    
    
    error=[]
    if test_page.status_code!=200:
        error.append('Please double check the ASIN. ')
    if error:
        return render_template('error.html',error_message=' '.join(error))
    else:
        df, G=get_result(app_vars['ASIN'],1,app_vars['maxn'])
        P=plot_net(df,G)
        script, div = components(P)
        
        return render_template('show_plot.html',prod_name=df['Name'][0],asin=df['ASIN'][0],
                               script_=script,div_=div,maxn=app_vars['maxn'])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
