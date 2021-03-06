#coding=utf-8

base_scores={
    'Ez': [31,64,99],
    'Nm': [72,150,234],
    'Hd': [126,262,408],
    'EX': [241,500,777],
}

lps={
    'Ez': 4,
    'Nm': 8,
    'Hd': 12,
    'EX': 20,
}

combos={
    'S': 1.08,
    'A': 1.06,
    'B': 1.04,
    'C': 1.02,
    '-': 1.,
}
scores={
    'S': 1.2,
    'A': 1.15,
    'B': 1.1,
    'C': 1.05,
    '-': 1.,
}
mods={
    '':1,
    ' +10':1.1,
    ' +5':1.05,
    ' +10+10': 1.1*1.1,
    ' +10+5': 1.1*1.05,
    ' +5+5': 1.05*1.05,
}

table={}
tuple_table={}
for mod,mk in mods.items():
    for mode,songs_itm in base_scores.items():
        for repeats, base_score in enumerate(songs_itm):
            for combo,ck in combos.items():
                for score,sk in scores.items():
                    pt=int(.5+base_score*ck*sk*mk)
                    table.setdefault(pt,[]).append('%s*%d %s:%s%s'%(mode,repeats+1,score,combo,mod))
                    tuple_table[pt]=(pt,repeats+1,lps[mode]*(repeats+1),0)

def parse_score(x):
    if x in table:
        if len(table[x])>3:
            return ' / '.join(table[x][:2])+' 等 %d 个'%len(table[x])
        else:
            return ' / '.join(table[x])

def parse_tuple(x):
    return tuple_table.get(x,(x,0,0,0))