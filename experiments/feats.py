#import seaborn as sb
import csv

p = "/Users/ruben/Documents/PhD/SECO-Assist/reproduction_package/random-forest/data/features.csv"

with open(p) as f:
    feats = list(csv.reader(f.readlines()))[1:]

COLS = {
    'Addition': 0,
    'Removal': 1,
    'Edit': 2,
    'Relocation': 3
}

ROWS = {}

max_unselect = 0.0
min_select = 1.0
for feat in feats:
    sign = float(feat[2]) if feat[2] else 0.0
    feat.append(sign)
    select = feat[1] == '1'
    if select:
        min_select = min(min_select, sign)
    else:
        max_unselect = max(max_unselect, sign)

avg = (max_unselect + min_select) / 2
for feat in feats:
    feat[3] -= avg

smax = max(feat[3] for feat in feats)
smin = min(feat[3] for feat in feats)

pos_rescale = 1 / smax
neg_rescale = -1 / smin

significances = [[], [], [], []]
vals = [[], [], [], []]

for (feat_name, rank, importance, sign) in feats:
    chg_kind = next(chg_kind for chg_kind in COLS.keys() if feat_name.endswith(chg_kind))
    comp_name = feat_name[:len(feat_name) - len(chg_kind)]
    col_nr = COLS[chg_kind]
    if comp_name in ROWS:
        row_nr = ROWS[comp_name]
    else:
        row_nr = len(ROWS)
        ROWS[comp_name] = row_nr
        for col in significances:
            col.extend([0] * (row_nr - len(col) + 1))
        for col in vals:
            col.extend(['N/A'] * (row_nr - len(col) + 1))

    vals[col_nr][row_nr] = importance if importance else 'N/A'
    significances[col_nr][row_nr] = sign * (pos_rescale if rank == '1' else neg_rescale)


print(significances)

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sb

#plot = sb.heatmap(np.array(significances).transpose(), cmap=sb.diverging_palette(12, 128, s=100, n=15), annot=np.array(vals).transpose(), fmt='',
#        xticklabels=[x[0] for x in sorted(COLS.items(), key=lambda x: x[1])],
#        yticklabels=[x[0] for x in sorted(ROWS.items(), key=lambda x: x[1])], cbar=False)
# plt.show()


cm = np.array([[46233, 1472, 31], [9894, 3866, 40], [1974, 684, 357]])
cmn = cm.astype('float') / cm.sum(axis=0)
print(cmn)
sb.set(font_scale=1.5)
plot = sb.heatmap(cmn, annot=cm, fmt='', cmap='Greens',
    xticklabels=['patch*', 'minor*', 'major*'], yticklabels=['patch', 'minor', 'major'])
plot.set_yticklabels(plot.get_yticklabels(), rotation=0)
plot.set_xlabel('Predicted')
plot.set_ylabel('Actual')
plt.savefig("foo.pdf", bbox_inches='tight')
