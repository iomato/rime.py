# -*- coding: utf-8 -*-
# vim:set et sts=4 sw=4:

class Model:
    def __init__ (self, schema):
        self.__db = schema.get_db ()
        self.__in_place_prompt = schema.get_in_place_prompt ()
    def update (self, ctx):
        m = 0
        while m < min (len (ctx.keywords), len (ctx.kwd)) and ctx.keywords[m] == ctx.kwd[m]:
            m += 1
        self.__invalidate_selections (ctx, m, len (ctx.kwd))
        del ctx.kwd[m:]
        for i in range (len (ctx.cand)):
            del ctx.cand[i][m - i:]
        del ctx.cand[m:]
        del ctx.sugg[m + 1:]
        for k in ctx.keywords[m:len (ctx.keywords) - self.__in_place_prompt]:
            ctx.kwd.append (k)
            ctx.cand.append ([])
            ctx.sugg.append (None)
            n = len (ctx.kwd)
            for i in range (max (0, n - 4), n):
                r = self.__db.lookup (ctx.kwd[i:])
                for x in r:
                    if n - i == 4 and self.__concatenated (ctx, i, x):
                        continue
                    self.__add_candidate (ctx, i, n - i, x)
        self.__calculate (ctx)
    def select (self, ctx, s):
        self.__invalidate_selections (ctx, s[0], s[0] + s[1])
        ctx.selection.append (s)
        for i in range (s[0] + 1, len (ctx.sugg)):
            ctx.sugg[i] = None
        self.__calculate (ctx)
    def __add_candidate (self, ctx, pos, length, x):
        c = ctx.cand[pos]
        if length > len (c):
            c += [[] for i in range (length - len (c))]
        c[length - 1].append (x)
    def __concatenated (self, ctx, pos, x):
        for i in range (pos):
            c = ctx.cand[i]
            j = pos + 3 - i - 1
            if j >= len (c):
                continue
            ok = False
            for y in c[j]:
                if y[0][-3:] == x[0][:3]:
                    self.__add_candidate (ctx, i, j + 2, (y[0] + x[0][-1], min (y[1], x[1])))
                    ok = True
            if ok:
                return True
        return False
    def __invalidate_selections (self, ctx, start, end):
        print '__invalidate_selections:', start, end
        if start >= end:
            return
        for s in ctx.selection:
            if s[0] < end and s[0] + s[1] > start:
                ctx.selection.remove (s)
    def __calculate (self, ctx):
        # update suggestion
        Free, Fixed = 0, 1
        sel = [Free] * len (ctx.kwd)
        for s in ctx.selection:
            for i in range (s[0], s[1] - 1):
                sel[i] = Fixed
            sel[s[0] + s[1] - 1] = s
        print sel
        def update_sugg (ctx, k, i, x):
            w = ctx.sugg[i][2] + 1 + 1.0 / (x[1] + 1)
            if not ctx.sugg[k] or w < ctx.sugg[k][2]:
                ctx.sugg[k] = (i, x[0], w)
        start = 0
        for k in range (1, len (ctx.sugg)):
            print 'k:', k
            s = sel[k - 1]
            if s == Fixed:
                pass
            elif s == Free:
                if ctx.sugg[k]:
                    continue
                for i in range (start, k):
                    if not ctx.sugg[i]:
                        continue
                    c = ctx.cand[i]
                    j = k - i
                    if j > len (c) or len (c[j - 1]) == 0:
                        continue
                    x = c[j - 1][0]
                    update_sugg (ctx, k, i, x)
            else:
                i, j, x = s[:]
                start = i + j
                print 'start:', start
                if ctx.sugg[k]:
                    continue
                if ctx.sugg[i]:
                    update_sugg (ctx, k, i, x)
        # update preedit
        k = len (ctx.sugg) - 1
        while k > 0 and not ctx.sugg[k]:
            k -= 1
        r = ctx.keywords[k:]
        t = ctx.sugg[k]
        split_words = lambda x: x.split () if u' ' in x else list (x)
        while t[0] != -1:
            r = split_words (t[1]) + r
            t = ctx.sugg[t[0]]
        ctx.preedit = r
        # update candidates
        #s = ctx.get_preedit ()
        ctx.candidates = []
        for pos in range (len (ctx.cand)):
            c = ctx.cand[pos]
            a = []
            for length in range (len (c), 0, -1):
                for x in c[length - 1]:
                    y = x[0]
                    #if s.startswith (y, pos):
                    #    continue
                    if length >= 4 and any ([t[0].startswith (y) for t in a]): 
                        continue
                    a.append ((y, (pos, length, x)))
            ctx.candidates.append (a)
