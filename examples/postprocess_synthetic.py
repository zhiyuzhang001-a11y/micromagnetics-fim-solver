"""Installed-package analytic example. No checkout path manipulation."""
from fimrun.postprocess.demo import generate
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args();rows=generate(a.output);print('rows:',len(rows))
