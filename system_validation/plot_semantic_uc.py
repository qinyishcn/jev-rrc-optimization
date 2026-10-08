"""Standalone scientific comparison figure from verified saved metrics."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    data=json.loads(Path("artifacts/semantic_uc/summary.json").read_text(encoding="utf-8"))["confirmation"]["metrics"]
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout="constrained")
    methods=["calibrated_fixed","tfidf","qwen_onepass","decider","known_intent"]
    names=["Fixed / numeric","TF-IDF + LR","Qwen one-pass","Decider + policy","Known intent"]
    values=[100*data[k]["deadline_miss_rate"] for k in methods]
    bars=axes[0].bar(names,values,color=["#9ba3af","#6387a8","#a68bb9","#d6773e","#558a6b"])
    axes[0].bar_label(bars,labels=[f"{v:.3f}%" for v in values],padding=3,fontsize=9)
    axes[0].set_ylim(0,max(values)*1.2)
    axes[0].set_ylabel("Packets lost or >20 ms (%)")
    axes[0].set_title("Confirmation: default option order")
    axes[0].tick_params(axis="x",labelrotation=18,labelsize=8)
    x=np.arange(2)
    for offset,variant,label,color in ((-.18,"","Original order","#d6773e"),(.18,"_reversed","Reversed order","#6387a8")):
        vs=[100*data[k+variant]["intent_accuracy"] for k in ("decider","qwen_onepass")]
        bars=axes[1].bar(x+offset,vs,width=.36,label=label,color=color)
        axes[1].bar_label(bars,labels=[f"{v:.1f}%" for v in vs],padding=3,fontsize=9)
    axes[1].set_xticks(x,["Decider","Qwen Base, one-pass"])
    axes[1].set_ylim(0,112)
    axes[1].set_ylabel("Dispatch-intent accuracy (%)")
    axes[1].set_title("48 unique texts x 3 fixed geometries")
    axes[1].legend(loc="lower right",fontsize=8)
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
    dest=Path("docs/figures/semantic_uc_comparison.png")
    dest.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(dest,dpi=180)
    print(dest)


if __name__=="__main__":
    main()
