import timeit
import os
import requests
import datetime
import csv
import json
import time
import urllib3
import random
from pathlib import Path
import glob
import string
import shutil
from datetime import timedelta
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


PPath=""
gui = 'FAE04EC0-301F-11D1-BF4B-00C04F79EFBC-GHFKJHF-IRHDHKHFDK-67890790'


def AppendFile(fname, el):
    try:
        if el is not None or el != '':
            el = el.strip('\n')
        with open(fname, 'at', encoding="utf-8") as myfile:
            myfile.write("%s\n" % el)
    except Exception as ex1:
        print("AppendFile() fname: " + fname + " Exception: " + ex1.__str__())
    return


def toJson(jsonvalue):
    """
    Convert object to JSON
    :param jsonvalue: string or dict for converting
    :return: tuple JSON,""   or return tuple None,ErrorText
    """
    try:
        ret = json.dumps(jsonvalue)
        return ret,""
    except Exception as ext:
        return None, ext.__str__()


def ParsingJson(jsonvalue):
    """
    Convert object to JSON
    :param jsonvalue: string or dict for converting
    :return: tuple JSON,""   or return tuple None,ErrorText
    """
    try:
        ret = json.loads(jsonvalue)
        return ret,""
    except Exception as ext:
        return None, ext.__str__()


def getCurDate(mform="%Y/%m/%d %H:%M:%S"):
    try:
        res = datetime.datetime.now().strftime(mform)
        return res
    except Exception as exw:
        tolog("getCurDate() Exception: "+exw.__str__())
        return ""


def combine(*s):
    return os.path.join(*s)



def CreateDir(dirname):
    try:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        return True
    except Exception as ex3:
        print("CreateDir() Exception: "+ex3.__str__())
        return False


def tolog(msg, fname="", isprint=False):
    global PPath
    try:
        if isNOE(fname):
            CreateDir(combine(PPath, "logs"))
            fname = combine(PPath, "logs", getCurDate("%Y-%m-%d") + ".log")
        if isNOE(msg):
            return
        AppendFile(fname, getCurDate() + " " + msg)
        if isprint:
            print(msg)
    except Exception as exa:
        print("tolog() exception: "+exa.__str__())


def AddTolog(fname, msg):
    AppendFile(fname, getCurDate() + " " + msg)


def MContains(st, subst):
    try:
        if subst.lower() in st.lower():
            return True
        else:
            return False
    except Exception:
        return False


def LoadCSV2(fname, delim=','):
    reslist = []
    try:
        with open(fname, "r", encoding="utf-8-sig") as csv_file:
            csvreader = csv.reader(csv_file, delimiter=delim)
            for row in csvreader:
                reslist.append(row)
        return reslist, ""
    except Exception as exc:
        print("LoadCSV2() fname: " + fname + " Exception: " + exc.__str__())
        return reslist, exc.__str__()


def tryget(ind, mlist):
    try:
        if not mlist:
            return ''
        res = mlist[ind]
        if isNOE(res):
            res = ""
        return res
    except Exception:
        # print("tryget() ind: " + str(ind) +" Exceptions: " + ex.__str__())
        return ''


def LoadCSV(fname):
    reslist = []
    try:
        cf = open(fname, 'r', newline='', encoding="utf-8-sig")
        reader = csv.reader(cf, lineterminator='\n')
        for row in reader:
            val = tryget(0,row)
            if isNOE(val):
                continue
            reslist.append(val)
        cf.close()
        return reslist
    except Exception as exg:
        print("LoasCSV() fname: " + fname + " Exception: " + exg.__str__())
        return reslist


def isNOE(self):
    if self is None or self == '' or not self:
        return True
    else:
        return False


def isNNOE(self):
    if self is None or self == '' or not self:
        return False
    else:
        return True


def MEqual(st1, st2):
    try:
        if st1.strip().lower() == st2.strip().lower():
            return True
        else:
            return False
    except Exception:
        return False


def MEqual(st1, st2):
    try:
        if st1 is None and st2 is None:
            return True
        if st1 is None and st2 is not None:
            return False
        if st2 is None and st1 is not None:
            return False
        if str(st1).strip().lower() == str(st2).strip().lower():
            return True
        else:
            return False
    except Exception:
        return False


def DelEmptyAndDuplicates(llist):
    retlist = []
    try:
        if len(llist) <= 0:
            return retlist
        llist = list(set(llist))
        for el in llist:
            if isNNOE(el):
                retlist.append(el)
        return retlist
    except Exception as exu:
        tolog("DelEmptyAndDuplicates() Exception: "+exu.__str__())
        return retlist


def LoadListFromFile(s,trimend=True, enc="utf-8-sig"):
    lines = []
    try:
        file = open(s, 'r',encoding=enc)
        lines = file.readlines()
        if trimend:
            lines = [line.rstrip('\n') for line in lines]
        file.close()
    except Exception as exd:
        print("LoadFileLines() Exception: "+exd.__str__())
    return lines


def Sleep(secs):
    time.sleep(secs)


def post_page(url, proxies, poststring, mheaders, mredirect=True, waittime=60, statuscode=200, count=10):

    for u in range(0, count):
        try:
            r = requests.post(url, data=poststring, headers=mheaders, verify=False, proxies=proxies, timeout=waittime, allow_redirects=mredirect)
            if r is None:
                continue
            if r.status_code == statuscode:
                return r.text.strip()
            else:
                pass

        except Exception as ex2:
            if "HTTPConnectionPool" in ex2.__str__() and "Read timed out" in ex2.__str__() and u >= 2:
                # print("post_page() url: " + url + " Exception: " + ex.__str__())
                return ""
            Sleep(5)
    return ""


def GetFiles(ldir, ext="*.*"):
    flist=[]
    try:
        for file in glob.glob(combine(ldir,ext)):
            flist.append(file)
        return flist
    except Exception as ex:
        tolog("GetFiles() Exception: "+ex.__str__())
        return flist


class mCookies:
    cname=""
    cvalue=""


class Webclient:
    gdic=[]
    cookies = dict()

    def __init__(self):
        pass

    def setconstcookies(self, mdic=None):
        try:
            if mdic is not None:
                self.gdic=mdic
            if len(self.gdic)>0:
                for el in self.gdic:
                    self.AddCookie(el.cname,el.cvalue)
        except Exception as ex:
            print('setconstcookies() Exception '+ex.__str__())

    def AddCookie(self, mname, mvalue):
        try:
            self.cookies.update({mname: mvalue})
        except Exception as ex:
            print('AddCookie() Exception '+ex.__str__())

    def get_page(self, url, proxies, mheaders, mredirect=True, waittime=60, statuscode=200, count=10):
        mretry=0
        for u in range(0, count):
            try:
                r = requests.get(url, headers=mheaders, proxies=proxies, timeout=waittime, cookies=self.cookies, verify=False, allow_redirects=mredirect)
                if r is None:
                    continue
                if r.status_code == statuscode:
                    self.cookies = r.cookies
                    text = r.text.replace('&amp;', gui)
                    text = text.replace('&amp', '&amp;')
                    text = text.replace(gui, '&amp;')
                    return text
                else:
                    mretry+=1
            except Exception as inst:
                pass
        return ""

    def post_page(self, url, poststring, proxies, mheaders, mredirect=True, waittime=90, statuscode=200, count=10):
        mretry = 0
        for u in range(0, count):
            try:

                r = requests.post(url, data=poststring, headers=mheaders, verify=False, timeout=waittime, proxies=proxies, cookies=self.cookies, allow_redirects=mredirect)
                if r is None:
                    continue
                if r.status_code == statuscode:
                    self.cookies = r.cookies
                    text = r.text.replace('&amp;', gui)
                    text = text.replace('&amp', '&amp;')
                    text = text.replace(gui, '&amp;')
                    return text
                else:
                    if u==count-1:
                        tolog(f"post_page() url: {url} ERROR: " + r.text)
                        return "ERROR: " + r.text
            except Exception as ex:
                return "ERROR: " + ex.__str__()
        return ""

    def put_page(self, url, poststring, proxies, mheaders, mredirect=True, waittime=90, statuscode=200, count=10):
        mretry = 0
        for u in range(0, count):
            try:

                r = requests.put(url, data=poststring, headers=mheaders, verify=False, timeout=waittime, proxies=proxies, cookies=self.cookies, allow_redirects=mredirect)
                if r is None:
                    continue
                if r.status_code == statuscode:
                    self.cookies = r.cookies
                    text = r.text.replace('&amp;', gui)
                    text = text.replace('&amp', '&amp;')
                    text = text.replace(gui, '&amp;')
                    if isNOE(text):
                        text= f"Success Update! Status code={r.status_code}"
                    return text
                else:
                    if u==count-1:
                        print("put_page() ERROR: " + r.text)
                        return "ERROR: " + r.text
            except Exception as ex:
                return "ERROR: " + ex.__str__()
        return ""



def RetryGet(link, headers, proxylist, webclient=None, maxretry=50):
    try:
        page = ""
        retrycount=0
        while True:
            retrycount = retrycount + 1
            if retrycount > maxretry:
                page=""
                break
            if webclient is None:
                webclient = Webclient()
            proxies = None
            if proxylist is not None:
                proxyindex = 0
                proxycount=len(proxylist)
                if proxycount > 0:
                    proxyindex = random.randint(0, proxycount - 1)
                    proxies = proxylist[proxyindex]

            page = webclient.get_page(link, proxies, headers, True, 120, 200, 1)
            if not page or page=='':
                time.sleep(0.3)
                continue
            if "403\n" in page:
                time.sleep(0.3)
                continue
            break
        return page
    except Exception as ex:
        tolog(f"RetryGet Exception: {ex.__str__()}")
        return ""



def RetryPut(link, poststr, headers, proxylist, webclient=None, cookies=None, maxretry=3, maxwait=120, retcode=200):
    try:
        page = ""
        retrycount = 0
        while True:
            retrycount = retrycount + 1
            if retrycount > maxretry:
                page = ""
                break
            if webclient is None:
                webclient = Webclient()
            if cookies is None:
                pass
            else:
                webclient.cookies = cookies
            proxies = None
            if proxylist is not None:
                proxycount = len(proxylist)
                if proxycount > 0:
                    proxyindex = random.randint(0, proxycount - 1)
                    proxies = proxylist[proxyindex]
            page = webclient.put_page(link, poststr, proxies, headers, True, maxwait, retcode, 1)
            if page == "Read timed out":
                return "Read timed out"
            if not page or page == '':
                time.sleep(0.3)
                continue
            if "403\n" in page:
                time.sleep(0.3)
                continue
            break
        return page
    except Exception as ex:
        tolog(f"RetryPut Exception: {ex.__str__()}")
        return ""


def CreateProxyList(lines, isHTTPS=True):
    proxylist = []
    try:
        for line in lines:
            try:
                arr = line.rstrip('\n').split(':')
                if len(arr)==2:
                    pp = "http://{0}:{1}".format(arr[0], arr[1])
                else:
                    pp = "http://{0}:{1}@{2}:{3}".format(arr[2], arr[3], arr[0], arr[1])
                proxylist.append({'http': pp, 'https': pp})
            except Exception as ex:
                tolog("CreateProxyList(1) "+ex.__str__())
    except Exception as ex:
        tolog("CreateProxyList(0) "+ex.__str__())
    return proxylist


def CreateFile(fname, fcontext, enc="utf-8-sig"):
    try:
        if fcontext is not None or fcontext != '':
            fcontext=fcontext.strip('\n')
        with open(fname, 'w', encoding=enc) as myfile:
            myfile.write("%s" % fcontext)
    except Exception as ex:
        tolog("CreateFile() fname: "+ fname+ " Exception: "+ex.__str__())
    return


def DelBefore(source, start, delword=True):
    origs=""
    try:
        origs = source
        source = source.lower()
        start = start.lower()
        if start in source:
            if delword:
                ind1 = source.find(start, 0)
                origs = origs[ind1 + start.__len__():].strip()
            else:
                ind1 = source.find(start, 0)
                origs = origs[ind1:].strip()
        return origs
    except Exception as ex:
        return origs


def DelAfter(source, start, delword=True):
    origs=""
    try:
        origs= source
        source = source.lower()
        start = start.lower()
        if start in source:
            if delword:
                ind1 = source.find(start, 0)
                origs = origs[0:ind1].strip()
            else:
                ind1 = source.find(start, 0)
                origs = origs[0:ind1+ start.__len__():].strip()
        return origs
    except Exception as ex:
        return origs


def FileExists(fname):
    try:
        my_file = Path(fname)
        if my_file.exists():
            return True
        else:
            return False
    except Exception as ex:
        tolog("FileExists Exception: "+ex.__str__())
        return False


def getCurrentDateTimeAddDay(mday=0):
    try:
        res = (datetime.datetime.now() + timedelta(days=mday))
        return res
    except Exception as ex:
        return None


def DelFile(fname):
    try:
        if FileExists(fname):
            os.remove(fname)
    except Exception as ex:
        print('DelFile() Exception: ' + ex.__str__())


def ClearOldLog(logpath, days):
    deleted = 0
    nowdt = getCurrentDateTimeAddDay(-days)
    try:
        for file in os.listdir(logpath):
            try:
                if file.endswith(".log"):
                    path = combine(logpath, file)
                    editdt = os.path.getctime(path)
                    dt_c = datetime.datetime.fromtimestamp(editdt)
                    if dt_c < nowdt:
                        DelFile(path)
                        if not FileExists(path):
                            deleted += 1
            except Exception as ex:
                pass
        return deleted
    except Exception as ex:
        tolog(f"ClearOldLog(logpath: {logpath}) Exception: {ex.__str__()}", isprint=False)
        return 0


def RetryPost(link, poststr, headers, proxylist, webclient=None, cookies=None, maxretry=50,maxwait=120, retcode=200):
    try:
        page = ""
        retrycount=0
        while True:
            retrycount = retrycount + 1
            if retrycount > maxretry:
                page=""
                break
            if webclient is None:
                webclient = Webclient()
            if cookies is None:
                pass
            else:
                webclient.cookies=cookies
            proxies = None
            if proxylist is not None:
                proxycount=len(proxylist)
                if proxycount > 0:
                    proxyindex = random.randint(0, proxycount - 1)
                    proxies = proxylist[proxyindex]
            page = webclient.post_page(link, poststr, proxies, headers, True, maxwait,retcode,1)
            if page=="Read timed out":
                return "Read timed out"
            if not page or page=='':
                time.sleep(0.3)
                continue
            if "403\n" in page:
                time.sleep(0.3)
                continue
            break
        return page
    except Exception as ex:
        tolog(f"RetryPost Exception: {ex.__str__()}")
        return ""



def ListToString(llist, divider=', '):
    res=""
    try:
        if len(llist) <=0:
            return ""
        res=divider.join(llist)
        return res
    except Exception as ex:
        tolog("ListToString")
        return res



def ParsingJson(jsonvalue):
    """
    Convert object to JSON
    :param jsonvalue: string or dict for converting
    :return: tuple JSON,""   or return tuple None,ErrorText
    """
    try:
        ret = json.loads(jsonvalue)
        return ret,""
    except Exception as ext:
        return None, ext.__str__()


def getJsonString(page, key):
    try:
        if page is None:
            return ""
        res = page[key]
        if res is None:
            return ""
        return str(res)
    except Exception as ex:
        return ""


def getJson(page, key):
    try:
        if page is None:
            return None
        res = page[key]
        return res
    except Exception as ex:
        return None


def getJsonNode(page, key):
    try:
        if page is None:
            return None
        res = page[key]
        return res
    except Exception as ex:
        return None


def getJsonInt(page, key):
    try:
        if page is None:
            return -1
        res = page[key]
        if res is None:
            return 0
        return int(res)
    except Exception as ex:
        return -1


def getJsonFloat(page, key):
    try:
        if page is None:
            return 0
        res = page[key]
        if res is None:
            return 0
        return float(res)
    except Exception as ex:
        return -1


def getJsonListToString(page, key, div=','):
    try:
        nodes = getJsonNode(page, key)
        if nodes is None:
            return ""
        else:
            llist = []
            for el in nodes:
                val = str(el)
                if isNOE(val):
                    continue
                else:
                    llist.append(val)
            ret = ListToString(llist, div)
            return ret
    except Exception as ex:
        tolog("getJsonListToString() "+ex.__str__())
        return ""


def is_only_digits(sstr):
    try:
        if isNOE(sstr):
            return False
        for el in sstr:
            if el not in string.digits:
                return False
        return True
    except Exception as ex:
        tolog("only_digit() exception: "+ex.__str__())
        return False


def MSplit(lstr, Split=" ", removeempty=False):
    res=[]
    if isNOE(lstr):
        return res
    try:
        arr=lstr.split(Split)
        if isListEmpty(arr):
            return res
        if removeempty:
            for el in arr:
                if isNOE(el):
                    continue
                else:
                    res.append(el)
        else:
            res = arr
    except Exception as ex:
        tolog("MSplit() Exception: "+ex.__str__())
    return res


def isListEmpty(mlist):
    try:
        if mlist is None:
            return True
        for el in mlist:
            if el is not None:
                return False
        return True
    except Exception:
        return True


def StringToFloat(value,retval=0.00):
    try:
        res=float(value)
        return res
    except:
        return retval


def StringToInt(value, retval=0):
    try:
        res=int(value)
        return res
    except:
        return retval


def StringToLong(value, retval=0):
    try:
        res=int(value)
        return res
    except Exception as ex:
        return retval



def GetFileNameWithoutExt(filepath):
    try:
        fn1 = os.path.splitext(filepath)[0]
        fn = os.path.basename(fn1)
        if isNOE(fn):
            fn = ""
        return fn
    except Exception as ex:
        return ""


def GetFileExt(filepath):
    filename, file_extension = os.path.splitext(filepath)
    return file_extension


def GetFileName(filepath, withext=True):
    try:
        base = os.path.basename(filepath)
        filename, file_extension = os.path.splitext(base)
        if withext:
            filename=filename+file_extension
        return filename
    except Exception as ex:
        tolog("GetFileName() "+ex.__str__())
        return ""


def GetPath(filepath):
    try:
        ret=os.path.dirname(filepath)
        return ret
    except Exception as ex:
        return ""


def DirExist(dirname):
    try:
        res=os.path.isdir(dirname)
        return res
    except Exception as ex:
        return False


def MStartWith(st, subst):
    try:
        if st.lower().startswith(subst.lower()):
            return True
        else:
            return False
    except Exception as ex:
        return False


def MEndWith(st, subst):
    try:
        if st.lower().endswith(subst.lower()):
            return True
        else:
            return False
    except Exception as ex:
        return False


def getCurPath():  # get script run path
    cp = ''
    try:
        cp = os.path.dirname(os.path.abspath(__file__))
    except Exception as ex2:
        tolog('getCurPath() Exception: ' + ex2.__str__())
    return cp


def Move_File(source, target):
    try:
        CreateDir(os.path.dirname(target))
        shutil.move(source, target)
        return ""
    except Exception as ex:
        err = f"Move_File() source: {source} target: {target} Exception: {ex}"
        tolog(err)
        return err


def SendFileMess(filepath, mess="", token="", chat_id=""):
    """
    Send a file through Telegram when token and chat_id are configured.
    Environment variables are kept as a fallback for older deployments.
    Return an empty string on success, or an error text.
    """
    try:
        token = (token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        chat_id = (chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
        if isNOE(token) or isNOE(chat_id):
            tolog(f"SendFileMess() skipped, telegram is not configured. file={filepath}")
            return ""
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(filepath, "rb") as fh:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": mess or ""},
                files={"document": fh},
                timeout=120,
            )
        if response.status_code == 200:
            return ""
        return f"Telegram status={response.status_code} body={response.text[:500]}"
    except Exception as ex:
        return f"SendFileMess() Exception: {ex}"
