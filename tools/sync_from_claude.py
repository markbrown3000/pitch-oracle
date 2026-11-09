# Copies the Claude version's leagues + predictions (22 main leagues) into the GitHub page's built-in data,
# so results reach the GitHub site the morning after the Claude refresh instead of waiting for football-data.co.uk.
# Matches already on the site keep their extra fields (Bet365 odds etc.); new matches take Bet365 odds from data/fixtures.csv.
# usage: python3 tools/sync_from_claude.py index.html <dir holding leagues/*.json and predictions/*.json> data/fixtures.csv
import json,sys,glob,csv,os
p,D,FX=sys.argv[1:4]
s=open(p,encoding='utf-8').read();k='window.PREDICTOR_BUILTIN=';i=s.index(k)+len(k);data,n=json.JSONDecoder().raw_decode(s[i:])
k2='window.PREDICTOR_FDNAMES=';j=s.index(k2)+len(k2);FDN,_=json.JSONDecoder().raw_decode(s[j:])
DIV={"E0":"epl","E1":"championship","E2":"league_one","E3":"league_two","EC":"national_league","SP1":"la_liga","SP2":"segunda","I1":"serie_a","I2":"serie_b","D1":"bundesliga","D2":"bundesliga_2","F1":"ligue_1","F2":"ligue_2","SC0":"scot_prem","SC1":"scot_champ","SC2":"scot_l1","SC3":"scot_l2","N1":"eredivisie","B1":"belgium","P1":"primeira","T1":"super_lig","G1":"greece"}
def num(x):
    try:return float(x)
    except:return None
b365={}
for r in csv.DictReader(open(FX,encoding='utf-8-sig')):
    c=DIV.get(r.get('Div'));nm=FDN.get(c,{}) if c else {}
    h,a=nm.get(r.get('HomeTeam')),nm.get(r.get('AwayTeam'))
    o=[num(r.get('B365'+x)) for x in 'HDA']
    if h and a and all(v and v>1 for v in o):
        dd,mm,yy=r['Date'].split('/');b365[(c,f"{yy if len(yy)==4 else '20'+yy}-{mm}-{dd}",h,a)]={"h":o[0],"d":o[1],"a":o[2]}
stat={"leagues":0,"new":0,"b365":0}
for f in glob.glob(D+'/leagues/*.json'):
    db=json.load(open(f));db=db.get('data',db);c=os.path.basename(f)[:-5]
    old=data['leagues'].get(c,{});om={(m['date'],m['home'],m['away']):m for m in old.get('matches',[])}
    L={**old,**db}
    for m in L['matches']:
        o=om.get((m['date'],m['home'],m['away']))
        if o:
            for kk,v in o.items(): m.setdefault(kk,v)
        else:
            stat['new']+=1
            if 'b365' not in m and (c,m['date'],m['home'],m['away']) in b365: m['b365']=b365[(c,m['date'],m['home'],m['away'])];stat['b365']+=1
    data['leagues'][c]=L;stat['leagues']+=1
for f in glob.glob(D+'/predictions/*.json'):
    db=json.load(open(f));db=db.get('data',db);data['predictions'][os.path.basename(f)[:-5]]=db
data['generatedAt']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
s=s[:i]+json.dumps(data,ensure_ascii=False,separators=(',',':'))+s[i+n:]
open(p,'w',encoding='utf-8').write(s);print(stat)
