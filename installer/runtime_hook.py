"""Windowed Python has no console streams; libraries can still log safely."""
import os
import sys
if sys.stdout is None:sys.stdout=open(os.devnull,'w',encoding='utf-8')
if sys.stderr is None:sys.stderr=open(os.devnull,'w',encoding='utf-8')
