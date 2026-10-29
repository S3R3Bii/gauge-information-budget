# Qualifier array support before analysis

The published USGS daily schema labels qualifier as string. The first fixed-gauge response instead has 1864 null qualifiers and359 arrays containing ESTIMATED. The original scalar-only type gate rejected the response. No flow values, fitted models, correlations or predictive errors were inspected.

The loader now accepts a null, documented scalar flag, or an array of bounded flag tokens and stores nonempty flags as canonical JSON arrays. Empty qualifiers remain empty. This preserves the flags and the predeclared sensitivity excluding nonempty qualifiers. Source dates, values, approval/coverage gates, pairs, periods and model rules are unchanged. Initial originals and failure hashes are retained privately; resume reuses exact saved bytes and compares final metadata versions rather than refreshing the snapshot.
