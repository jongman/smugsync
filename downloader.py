#!/usr/bin/python
import urllib
import smugmug
import argparse
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("album_id")
    parser.add_argument("album_key")
    parser.add_argument("size", choices=["Small", "Medium", "Large", "XLarge",
                                         "X2Large", "X3Large", "Original"])
    parser.add_argument("target")
    parser.add_argument("--movies", action="store_true", default=False)
    args = parser.parse_args()
    print args
    api = smugmug.API()
    api.login()
    images = api.get_images(args.album_id, args.album_key, {"Heavy": "true"})
    for img in images:
        if img["FileName"].lower().endswith("mov") and not args.movies:
            continue
        dest = os.path.join(args.target, img["FileName"])
        if os.path.exists(dest): continue
        print "downloading %s .." % img["FileName"]
        open(dest, "wb").write(urllib.urlopen(img[args.size + "URL"]).read())


