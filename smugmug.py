# -*- coding: utf-8 -*-

from config import *

API_VERSION='1.2.2'
API_URL='https://api.smugmug.com/hack/json/1.2.0/'
UPLOAD_URL='http://upload.smugmug.com/photos/xmlrawadd.mg'
import sys, re, urllib, urllib2, urlparse, hashlib
import traceback, os.path, json, logging

class API(object):
    def __init__(self):
        self.session = self.su_cookie = None

    def login(self):
        res = self._call("smugmug.login.withPassword",
                {"APIKey": SMUGMUG_API,
                 "EmailAddress": SMUGMUG_ID,
                 "Password": SMUGMUG_PASSWORD})
        self.session = res["Login"]["Session"]["id"]

    def get_albums(self):
        return self._call("smugmug.albums.get")["Albums"]

    def get_categories(self):
        cate = self._call("smugmug.categories.get")
        return dict((d["Title"], d["id"]) for d in cate["Categories"])

    def create_album(self, name, category, options={}):
        options.update({"Title": name, "CategoryID": category})
        return self._call("smugmug.albums.create", options)["Album"]["id"]

    def upload(self, path, album_id, hidden=False, options={}):
        data = open(path, "rb").read()
        args = {'Content-Length'  : len(data),
                'Content-MD5'     : hashlib.md5(data).hexdigest(),
                'Content-Type'    : 'none',
                'X-Smug-SessionID': self.session,
                'X-Smug-Version'  : API_VERSION,
                'X-Smug-ResponseType' : 'JSON',
                'X-Smug-AlbumID'  : str(album_id),
                'X-Smug-Hidden'   : str(hidden),
                'X-Smug-FileName' : os.path.basename(path) }
        args.update(options)
        request = urllib2.Request(UPLOAD_URL, data, options)
        return self._http_request(request)["stat"]

    def _call(self, method, params={}):
        if self.session and "SessionID" not in params:
            params["SessionID"] = self.session
        paramstrings = [urllib.quote(key) + "=" + urllib.quote(val) 
                for key, val in params.iteritems()]
        paramstrings += ['method=' + method]
        url = urlparse.urljoin(API_URL, '?' + '&'.join(paramstrings))
        request = urllib2.Request(url)
        if self.su_cookie:
            request.add_header("Cookie", self.su_cookie)
        return self._http_request(request)

    def _http_request(self, request):
        for it in xrange(5):
            try:
                response_obj = urllib2.urlopen(request)
                response = response_obj.read()
                result = json.loads(response)

                meta_info = response_obj.info()
                if meta_info.has_key("set-cookie"):
                    match = re.search('(_su=\S+);', meta_info["set-cookie"])
                    if match and match.group(1) != "_su=deleted":
                        self.su_cookie = match.group(1)
                if result["stat"] != "ok":
                    raise Exception("Bad result code")
                return result
            except:
                continue
        logging.info("API request failed. Request was:\n%s\n"
                "Response was:\n%s", request.get_full_url(),
                str(response))
        raise Exception("bah")

if __name__ == "__main__":
    api = API()
    api.login()
    print api.get_albums()
