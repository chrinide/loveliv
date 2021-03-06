import requests
import pyquery
import sqlite3
import datetime
import time
import os
from utils import log, init_db, init_master, parse_score_meta
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('-e',nargs='?',dest='EVENT_ID',help='Specify event id')
parser.add_argument('-b',nargs='*',dest='BUGGY_USERS',help='User INDs that will skip errors when fetching')
parser.add_argument('-c',dest='CRAWL_HTML',action='store_true',help='Crawl HTML-Formatted line data instead of JSON API')
parser.add_argument('-f',dest='FUCK_LINE',action='store_true',help='DO NOT fetch the line anymore')
args=parser.parse_args()
assert not args.CRAWL_HTML or args.EVENT_ID is not None, 'EVENT_ID is needed with CRAWL_HTML flag'

s=requests.Session()

TIMEOUT=30
INF=999999
err_level=0

def push(x):
    print(' -> add push:',x.replace('\n','\\n'))
    with sqlite3.connect('events.db') as db:
        db.execute(
            'insert into push_msgs (content) values (?)',
            ['%s %s'%(datetime.datetime.now().strftime('%m-%d %H:%M'),x)]
        )

def line_num(x):
    return -1 if x<=0 else 1 if x<=2300 else 2 if x<=11500 else 3 if x<=23000 else 4 if x!=INF else -1

def _fetch_user_rank(ind,uid,eventid):
    global err_level
    try:
        res=s.get(
            'https://siflive.umisonoda.com/ranking.php',
            params={
                'pos':'',
                'userId':uid,
                'event_id':eventid,
            },
            timeout=TIMEOUT,
        )
        res.raise_for_status()
        res.json()
    except Exception as e:
        if last_user_score[ind] is not None:
            if ind not in BUGGY_USERS:
                err_level+=3
                log('error','%d 的分数获取失败，使用上次结果：[%s] %s'%(uid,type(e),e))
            return {
                'score': last_user_score[ind][1],
                'rank': last_user_score[ind][2],
                'level': last_user_score[ind][0],
            }
        elif ind in BUGGY_USERS:
            return {
                'score': 0,
                'rank': INF,
                'level': -1,
            }
        else:
            raise
        
    for user in res.json()['data']:
        if user['user_data']['user_id']==uid:
            return {
                'score': user['score'],
                'rank': user['rank'],
                'level': user['user_data']['level'],
            }
    else:
        if last_user_score[ind] is not None:
            if ind not in BUGGY_USERS:
                err_level+=3
                log('error','%d 的分数无效，使用上次结果'%uid)
            return {
                'score': last_user_score[ind][1],
                'rank': last_user_score[ind][2],
                'level': last_user_score[ind][0],
            }
        else:
            if ind not in BUGGY_USERS:
                err_level+=3
                log('error','%d 的分数无效'%uid)
            return {
                'score': 0,
                'rank': INF,
                'level': -1,
            }

def _fetch_line():
    if args.FUCK_LINE:
        wtf={'predict':0,'current':0}
        return evt_info_bkp, {'2300': wtf, '11500': wtf, '23000': wtf}

    if args.CRAWL_HTML:
        evt_info=evt_info_bkp
        res=s.get('http://2300.ml/',timeout=TIMEOUT)
        res.raise_for_status()
        pyq=pyquery.PyQuery(res.text)
        predict={
            '2300': {'predict': int(pyq('#pred_2300').text()), 'current': int(pyq('#curr_2300').text())},
            '11500': {'predict': int(pyq('#pred_11500').text()), 'current': int(pyq('#curr_11500').text())},
            '23000': {'predict': int(pyq('#pred_23000').text()), 'current': int(pyq('#curr_23000').text())},
        }


    else:
        res=s.get('http://2300.ml/api/json',timeout=TIMEOUT)
        res.raise_for_status()
        j=res.json()

        if args.EVENT_ID is not None:
            evt_info=evt_info_bkp
        else:
            evt_info={
                'id': int(j['event_info']['event_id']),
                'title': j['event_info']['title'],
                'begin': datetime.datetime.strptime(j['event_info']['begin'],'%Y-%m-%d %H:%M:%S'),
                'end': datetime.datetime.strptime(j['event_info']['end'],'%Y-%m-%d %H:%M:%S'),
            }

        predict=j['predictions']
        for scores in ['2300','11500','23000']:
            if scores not in predict:
                predict[scores]={'predict':0,'current':0}

    return evt_info, predict

last_line_result=None
if not os.path.exists('events.db'):
    print(' -> initializing master db...')
    init_master()
with sqlite3.connect('events.db') as _db:
    _cur=_db.execute('select ind,id,name from follows')
    follows=_cur.fetchall() # [(ind, user_id, name), ...]
    print(' -> got %d user(s) to follow'%len(follows))
    last_user_score={x[0]:None for x in follows} # {ind: (level, score, rank), ...}

def _fetchall():
    global last_line_result
    global err_level
    
    print(' == fetching line')
    try:
        evt_info,predict=_fetch_line()
    except Exception as e:
        if last_line_result:
            err_level+=3
            log('error','档线获取失败，使用上次结果')
            evt_info,predict=last_line_result
        else:
            raise
    else:
        last_line_result=evt_info,predict
    
    eventid=evt_info['id']
    score_parser=parse_score_meta(eventid)

    if not os.path.exists('db/%d.db'%eventid): # init db
        print(' -> new event: event #%d %s'%(eventid,evt_info['title']))
        print(' -> creating database and writing event info...')
        init_db(eventid)
        with sqlite3.connect('events.db') as db:
            db.execute(
                'insert or replace into events (id, title, begin, end, last_update, score_parser) '
                'values (?,?,?,?,null,(select score_parser from events where id=?))',
                [eventid,evt_info['title'],int(evt_info['begin'].timestamp()),int(evt_info['end'].timestamp()),eventid]
            )
    if datetime.datetime.now()-datetime.timedelta(minutes=3)>evt_info['end']:
        log('debug','活动 #%d 结束，爬虫停止抓取'%eventid)
        push('[SYSTEM]\n活动 #%d 结束\n#2300 : %d pt\n#11500 : %d pt\n#23000 : %d pt'%(
            eventid,predict['2300']['current'],predict['11500']['current'],predict['23000']['current']))
        raise SystemExit('活动结束')

    with sqlite3.connect('db/%d.db'%eventid) as db:
        db.execute('insert into line (time, t1pre, t1cur, t2pre, t2cur, t3pre, t3cur) values (?,?,?,?,?,?,?)', [
            int(datetime.datetime.now().timestamp()),
            predict['2300']['predict'], predict['2300']['current'],
            predict['11500']['predict'], predict['11500']['current'],
            predict['23000']['predict'], predict['23000']['current'],
        ])
        for ind,uid,name in follows:
            print(' == fetching score of #%d %s at place %d'%(uid,name,ind))
            details=_fetch_user_rank(ind,uid,eventid)

            if last_user_score[ind] is not None:
                last_lv, last_score, last_rank=last_user_score[ind]

                if details['score']!=last_score:
                    score_delta=details['score']-last_score
                    log('info','关注者 %s 分数变更：%d pt + %d pt → %d pt%s'%\
                        (name,last_score,score_delta,details['score'],score_parser(score_delta,' (%s)')))
                    if last_score and details['score']>0:
                        push('%s\n%s获得了 %d pt\n→ %d pt (#%d)'%\
                            (name,score_parser(score_delta,'进行了 %s\n'),score_delta,details['score'],details['rank']))

                if details['level']!=last_lv:
                    log('info','关注者 %s 等级变更：lv %d → lv %d'%(name,last_lv,details['level']))
                    if last_user_score[ind][0]>0 and details['level']>0:
                        push('%s\n升级到了 lv. %d'%(name,details['level']))

                if line_num(details['rank'])!=line_num(last_rank):
                    better_line=min(line_num(last_rank),line_num(details['rank']))
                    log('info','关注者 %s 档位变更：L%d → L%d (#%d)'%\
                        (name,line_num(last_rank),line_num(details['rank']),details['rank']))
                    if line_num(last_rank)>0 and line_num(details['rank'])>0:
                        push('%s\n%s了 %d 档\n当前排名：#%d'%\
                             (name,'离开' if better_line==line_num(last_rank) else '进入',better_line,details['rank']))

            last_user_score[ind]=(details['level'],details['score'],details['rank'])

            db.execute(
                'insert into follow%d (time,level,score,rank) values (?,?,?,?)'%ind,
                [int(datetime.datetime.now().timestamp()), details['level'], details['score'], details['rank']]
            )

    return eventid

def mainloop():
    global err_level
    in_err_mode=False
    
    print('=== servant started')
    curmin=datetime.datetime.now().minute
    log('success','LoveLiv Servant 已启动，关注者共有 %d 人'%len(follows))

    while True:    
        if err_level>=30:
            if in_err_mode:
                err_level=30
            else:
                in_err_mode=True
                push('[SYSTEM]\n这破网烂得我都报警了')
                    
        print(' -> waiting for next update...')
        while curmin==datetime.datetime.now().minute:
            time.sleep(1)

        curmin=datetime.datetime.now().minute
        print('=== ticked at %s'%datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        tstart=time.time()
        eventid=None
        bug=None
        last_errlevel=err_level
        try:
            eventid=_fetchall()
        except Exception as e:
            err_level+=3
            bug='[%s] %s'%(type(e),e)
            print('!!!',bug)
        except SystemExit:
            bug='活动结束'
            return
        else:
            if err_level<=0:
                if in_err_mode:
                    in_err_mode=False
                    push('[SYSTEM]\n这破网好像缓过来了')
                err_level=0
            elif last_errlevel==err_level: #no error this turn
                err_level-=4
            
            bug=None
            with sqlite3.connect('events.db') as db:
                db.execute(
                    'update events set last_update=? where id=?',
                    [int(datetime.datetime.now().timestamp()), eventid]
                )
            print(' == update completed')
        finally:
            if bug is not None:
                log('error','爬取出错，用时 %.1f 秒：%s'%(time.time()-tstart,bug))
            else:
                pass
                #log('debug','活动 #%s 爬取成功，用时 %.1f 秒'%(eventid,time.time()-tstart))

if args.EVENT_ID:
    print(' -> EVENT_ID specified. fetching details...')
    eres=s.get('http://sifcn.loveliv.es/api/event_meta/%s' % args.EVENT_ID)
    eres.raise_for_status()
    ej=eres.json()
    evt_info_bkp={
        'id': int(ej['event_id']),
        'title': ej['title'],
        'begin': datetime.datetime.strptime(ej['begin']['time'], '%Y-%m-%d %H:%M:%S'),
        'end': datetime.datetime.strptime(ej['end']['time'], '%Y-%m-%d %H:%M:%S'),
    }
BUGGY_USERS=[int(x) for x in args.BUGGY_USERS or []]

mainloop()
