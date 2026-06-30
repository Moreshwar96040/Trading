"""
Pure-numpy fallback learner: gradient-boosted depth-2 regression trees.
Used ONLY when neither LightGBM nor scikit-learn is installed, so the
pipeline runs with just numpy + pandas. On your machine, install the
requirements and the far stronger LightGBM/sklearn engines take over.
"""
import numpy as np


class _Stump:
    __slots__ = ("feat", "thr", "left", "right", "lval", "rval",
                 "l_node", "r_node")

    def fit(self, X, g, depth):
        n, m = X.shape
        best = (1e18, None, None)
        # subsample features for speed
        feats = np.random.default_rng(depth + n).choice(m, size=min(m, 12), replace=False)
        for f in feats:
            xs = X[:, f]
            qs = np.quantile(xs, [0.25, 0.5, 0.75])
            for thr in qs:
                mask = xs <= thr
                if mask.sum() < 5 or (~mask).sum() < 5:
                    continue
                lv, rv = g[mask].mean(), g[~mask].mean()
                err = ((g[mask] - lv) ** 2).sum() + ((g[~mask] - rv) ** 2).sum()
                if err < best[0]:
                    best = (err, f, thr, lv, rv, mask)
        if best[1] is None:
            self.feat = -1
            self.lval = g.mean()
            return self
        _, f, thr, lv, rv, mask = best
        self.feat, self.thr = f, thr
        self.l_node = self.r_node = None
        if depth > 1 and mask.sum() > 20 and (~mask).sum() > 20:
            self.l_node = _Stump().fit(X[mask], g[mask], depth - 1)
            self.r_node = _Stump().fit(X[~mask], g[~mask], depth - 1)
            self.lval = self.rval = None
        else:
            self.lval, self.rval = lv, rv
        return self

    def predict(self, X):
        if self.feat == -1:
            return np.full(X.shape[0], self.lval)
        mask = X[:, self.feat] <= self.thr
        out = np.empty(X.shape[0])
        if self.l_node is not None:
            out[mask] = self.l_node.predict(X[mask])
            out[~mask] = self.r_node.predict(X[~mask])
        else:
            out[mask] = self.lval
            out[~mask] = self.rval
        return out


class NumpyGBR:
    def __init__(self, n_estimators=120, learning_rate=0.05, max_depth=3, **kw):
        self.n = int(n_estimators)
        self.lr = float(learning_rate)
        self.depth = int(max_depth if max_depth and max_depth > 0 else 3)
        self.trees = []
        self.base = 0.0

    def fit(self, X, y):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.base = y.mean()
        pred = np.full_like(y, self.base)
        self.trees = []
        for _ in range(self.n):
            resid = y - pred
            t = _Stump().fit(X, resid, self.depth)
            pred = pred + self.lr * t.predict(X)
            self.trees.append(t)
        return self

    def predict(self, X):
        X = np.asarray(X, float)
        out = np.full(X.shape[0], self.base)
        for t in self.trees:
            out += self.lr * t.predict(X)
        return out
