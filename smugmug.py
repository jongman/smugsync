# -*- coding: utf-8 -*-

import config
import re, urllib, urllib2, urlparse, hashlib
import os.path, json, logging

API_VERSION='1.2.2'
API_URL='https://secure.smugmug.com/services/api/json/1.2.2/'
UPLOAD_URL='http://upload.smugmug.com/photos/xmlrawadd.mg'

class SmugmugException(Exception):
    def __init__(self, response):
        self.response = response
        super(Exception, self).__init__()
    pass

class API(object):
    def __init__(self):
        self.session = self.su_cookie = None

    def login(self):
        res = self._call("smugmug.login.withPassword",
                {"APIKey": config.SMUGMUG_API,
                 "EmailAddress": config.SMUGMUG_ID,
                 "Password": config.SMUGMUG_PASSWORD})
        self.session = res["Login"]["Session"]["id"]

    def get_albums(self):
        return self._call("smugmug.albums.get")["Albums"]

    def get_images(self, album_id, album_key):
        return self._call("smugmug.images.get", {"AlbumID": album_id,
            "AlbumKey": album_key})["Album"]["Images"]

    def change_image_setting(self, image_id, args={}):
        args = dict(args)
        args["ImageID"] = image_id
        return self._call("smugmug.images.changeSettings", args)

    def get_categories(self):
        cate = self._call("smugmug.categories.get")
        return dict((d["Name"], d["id"]) for d in cate["Categories"])

    def get_subcategories(self, category_id):
        try:
            cate = self._call("smugmug.subcategories.get",
                    {"CategoryID": category_id})
            return dict((d["Name"], d["id"]) for d in cate["SubCategories"])
        except SmugmugException as e:
            resp = e.response
            if isinstance(resp, dict) and resp["code"] == 15:
                return []
            raise

    def create_subcategory(self, category_id, name):
        logging.info("Creating subcategory %s ..", name)
        return self._call("smugmug.subcategories.create",
                {"CategoryID": category_id, "Name":
                    name})["SubCategory"]["id"]


    def create_album(self, name, category, options={}):
        logging.info("Creating album %s ..", name)
        options.update({"Title": name, "CategoryID": category})
        logging.debug("create_album %s", str(options))
        return self._call("smugmug.albums.create", options)["Album"]["id"]

    def upload(self, path, album_id, hidden=False, options={}):
        data = open(path, "rb").read()
        args = {'Content-Length'  : len(data),
                'Content-MD5'     : hashlib.md5(data).hexdigest(),
                'Content-Type'    : 'none',
                'X-Smug-SessionID': self.session,
                'X-Smug-Version'  : API_VERSION,
                'X-Smug-ResponseType' : 'JSON',
                'X-Smug-AlbumID'  : album_id,
                'X-Smug-FileName' : os.path.basename(path) }
        args.update(options)
        if hidden:
            args['X-Smug-Hidden'] = 'true'
        logging.debug("Uploading %s ..", path)
        request = urllib2.Request(UPLOAD_URL, data, args)
        return self._http_request(request)["stat"]

    def _call(self, method, params={}):
        if self.session and "SessionID" not in params:
            params["SessionID"] = self.session
        paramstrings = [urllib.quote(str(key)) + "=" + urllib.quote(str(val))
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
                    raise SmugmugException(result)
                return result
            except SmugmugException as e:
                logging.error("SmugmugException: %s", str(e.response))
                raise
            except Exception as e:
                logging.error("Exception during request: %s", str(e))
                continue
        logging.info("API request failed. Request was:\n%s\n"
                "Response was:\n%s", request.get_full_url(),
                str(response))
        raise SmugmugException(response)

if __name__ == "__main__":
    api = API()
    api.login()
    print api.get_albums()
