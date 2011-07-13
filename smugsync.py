#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import shelve
from config import *

PROJECT_PATH = os.path.dirname(__file__)
SHELF_PATH = os.path.join(PROJECT_PATH, "shelf.db")

def main():
    global shelf
    shelf = shelve.open(SHELF_PATH)
    shelf.close()

if __name__ == "__main__":
    main()
