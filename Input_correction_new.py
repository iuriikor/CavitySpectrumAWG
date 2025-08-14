import numpy as np

def amplitude_correction(input, f):
    #print(f)
    newinput = input/(1-(f*10**(-6)*0.0026958273609810437 - 0.014612921065786618))     #newinput as a function of input frequency fitted with linear function ((input-output)/input = k*f + d)(relative deviation independent of input amp)
    return newinput

def phase_correction(input): return input + 7.273520725378345/360*2*np.pi
