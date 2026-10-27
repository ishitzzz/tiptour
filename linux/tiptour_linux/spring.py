"""Exact damped mass-1 spring step for a target held over one frame.

Response and damping match the pinned Mac settings. This solves the spring
model, not SwiftUI's private animation implementation or retargeting behavior.
"""
import math

def step(position, velocity, target, elapsed, response=0.2, damping=0.6):
    if elapsed <= 0:return position, velocity
    omega=2*math.pi/response
    decay=damping*omega
    frequency=omega*math.sqrt(1-damping*damping)
    offset=position-target
    b=(velocity+decay*offset)/frequency
    sine=math.sin(frequency*elapsed);cosine=math.cos(frequency*elapsed)
    attenuation=math.exp(-decay*elapsed)
    displacement=offset*cosine+b*sine
    return (target+attenuation*displacement,
            attenuation*(-decay*displacement+frequency*(-offset*sine+b*cosine)))
