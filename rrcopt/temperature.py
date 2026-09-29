"""Choice temperature and confidence fallback for already measured Decider logits.

For one Choice question, all option logits share a positive scalar temperature.
Changing that scalar changes probabilities but never the preferred option.
"""
import math


def rescale(probabilities: dict[str, float], old_t: float, new_t: float) -> dict[str, float]:
    if not (math.isfinite(old_t) and old_t>0 and math.isfinite(new_t) and new_t>0):
        raise ValueError('Temperatures must be positive and finite')
    if len(probabilities)<2 or any(not math.isfinite(p) or p<0 for p in probabilities.values()) or abs(sum(probabilities.values())-1)>1e-5:
        raise ValueError('Expected a normalized nonnegative Choice distribution')
    logits={name:(old_t/new_t)*math.log(p) if p>0 else -math.inf for name,p in probabilities.items()}
    pivot=max(logits.values())
    exps={name:math.exp(v-pivot) for name,v in logits.items()}
    total=sum(exps.values())
    return {name:value/total for name,value in exps.items()}


def choose_with_fallback(probabilities: dict[str,float], threshold: float, fallback: str) -> str:
    if not 0<=threshold<=1 or fallback not in probabilities:
        raise ValueError('Invalid threshold or fallback')
    name=max(probabilities,key=probabilities.__getitem__)
    return name if probabilities[name]>=threshold else fallback
