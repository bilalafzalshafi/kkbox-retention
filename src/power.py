"""Approximate fixed-sample two-proportion design, independent subscribers."""
import math
from statistics import NormalDist

def sample_size(p0=.70, uplift=.03, alpha=.05, power=.80):
    p1=p0+uplift
    if not 0<p0<1 or not 0<p1<1 or uplift==0 or not 0<alpha<1 or not 0<power<1:
        raise ValueError('Invalid design probabilities')
    z=NormalDist();pa=(p0+p1)/2
    numerator=z.inv_cdf(1-alpha/2)*math.sqrt(2*pa*(1-pa))+z.inv_cdf(power)*math.sqrt(p0*(1-p0)+p1*(1-p1))
    return math.ceil(numerator*numerator/(uplift*uplift))

if __name__=='__main__':
    for effect in [.02,.03,.05]:
        n=sample_size(uplift=effect)
        print(f'Assumed p0=.70, effect={effect:.0%}: {n:,}/arm; {2*n:,} total')
