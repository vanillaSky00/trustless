# Clustering for Zero Trust Anomaly Detection

**Scenario:** Zero Trust Network — Contextual Access Anomaly Detection
**Dataset:** CERT Insider Threat r4.2 — `logon.csv` (Kaggle: `mrajaxnp/cert-insider-threat-detection-research`)
**Implementation:** Python with RAPIDS cuML/cuDF on NVIDIA T4 (Google Colab)


## 1. The Problem We're Trying to Solve

Zero Trust Architecture, as defined in NIST SP 800-207, requires every access request to be evaluated against context — not just credentials. Every login event must be assessed by asking *who* is connecting, *from what device*, *at what time*, and *to what resource*.

This makes the security problem fundamentally **anomaly-shaped**, not partition-shaped:

- The vast majority of user activity is legitimate, routine, and densely packed in feature space.
- A small minority of activity is unusual — and these are exactly what a Policy Decision Point needs flagged for verification.
- We have **no labels** at the user-day level — real ZTN telemetry doesn't come with "this is suspicious" tags. We must learn what's normal from the data itself.

This is why **unsupervised clustering** is the right tool, and why **DBSCAN specifically** is the right algorithm for this problem.


## 2. Why DBSCAN, Not K-Means

The choice of algorithm is the central methodological decision. Here is why DBSCAN fits the ZTN scenario where K-Means does not:

| Property | K-Means | DBSCAN | What ZTN needs |
|---|---|---|---|
| Predefined cluster count | Required (`k`) | Not needed | Not needed — we don't know how many normal patterns exist |
| Output for outliers | Forced into nearest cluster | Marked as `noise = -1` | A discrete "flag for verification" signal |
| Cluster shape | Round, well-separated | Arbitrary shape | Real behavior is irregular |
| Imbalance handling | Sensitive | Native | ZTN data is 95%+ normal |
| Output semantics | Partition (every point assigned) | Density (some points are nowhere) | Density |

The key word is **noise**. DBSCAN is the only common clustering algorithm that explicitly says "this point doesn't belong to any cluster" — and that is exactly the output a Zero Trust pipeline needs. Every noise point becomes a candidate incident requiring verification.


## 3. The Aggregation Decision: User-Days, Not Logon Events

The CERT dataset contains ~3.5 million raw logon events. A single event ("user X logged on at time Y on machine Z") tells us nothing about whether behavior is anomalous — anomaly is a property of *patterns*, not of single events.

The critical modeling decision is to aggregate to **one row per (user, day)**:

| Feature | Meaning | What it captures |
|---|---|---|
| `n_events` | Total logon/logoff events that day | Activity volume |
| `n_logons` | Distinct logon actions | Session count |
| `n_distinct_pcs` | Number of different machines used | Device hopping |
| `n_after_hours` | Events outside 07:00–19:00 | Temporal anomaly |
| `n_weekend` | Events on Saturday/Sunday | Off-cycle activity |
| `first_hour` | Earliest hour of activity | Early-morning starts |
| `last_hour` | Latest hour of activity | Late-night ends |
| `hour_span` | Last hour − first hour | Day length |

Each user-day is now a single point in 8-dimensional behavioral space, and clustering is asking: *"Which user-days have similar behavioral fingerprints?"*

This 8D feature space directly encodes NIST SP 800-207's **who / where / when** contextual signals.


## 4. The Pipeline

After Task 2 clustering completed on Google Colab with RAPIDS GPU acceleration, the full pipeline was:

1. **Load** ~3.5M logon events into cuDF
2. **Aggregate** to user-day profiles (~1.39M rows)
3. **Sample** 100,000 user-days (T4 memory ceiling for DBSCAN)
4. **Standardize** features — critical because DBSCAN uses Euclidean distance
5. **Reduce dimensions** with PCA + UMAP for visualization (DBSCAN itself runs on the full 8D space)
6. **k-distance plot** to choose `eps` from the elbow
7. **DBSCAN fit** + **K-Means baseline** (k=2..8, silhouette selection)
8. **Profile** the noise points — characterize what makes anomalous user-days different


## 5. Pre-Clustering Visualization: PCA vs UMAP

Before running any clustering, both PCA and UMAP were used to visualize the raw structure of the data.

### What PCA showed

PCA captured **71.3% of variance in 2D** — a high number indicating behavior is mostly low-rank (linear combinations of features carry most of the signal). Visually, PCA produced a fan-shaped cloud with a small detached splinter group.

The **fan structure** is the imprint of integer-valued features: `n_events`, `n_logons`, etc. take small whole-number values that, when projected linearly, produce discrete diagonal stripes rather than a smooth blob.

### What UMAP showed

UMAP produced a **starfield of ~80-90 dense polka dots** scattered across the 2D plane. Each dot is a recurring behavioral pattern — a "shift signature" — that many users follow on many days.

The contrast is informative: same data, two visualizations, very different appearances. PCA preserves variance (linear). UMAP preserves neighborhoods (nonlinear). The fact that UMAP reveals 80+ distinct dots while PCA shows one smear means the cluster structure is **nonlinearly separable** — exactly the kind of structure DBSCAN (which uses density, not linear projections) was designed to find.

### Why this matters

The pre-clustering view answered an important question: *was DBSCAN even appropriate here?* The UMAP polka-dot pattern showed it was. Many small dense regions with sparse points scattered between them is the canonical use case for density-based methods.


## 6. The k-Distance Plot — Principled `eps` Selection

DBSCAN's most sensitive parameter is `eps`, the radius defining "close enough to be a neighbor." Choosing it by guesswork is how people get bad clusters. The principled method:

> *"For every point, measure the distance to its k-th nearest neighbor. Sort all those distances. The elbow of the resulting curve is your `eps`."*

With `min_samples = 16` (rule of thumb: ≈ 2 × n_features), the k-distance plot showed something striking:

```
Zone 1 — Flat at 0 (95% of points): "I have 16+ exact behavioral twins"
Zone 2 — Curve rising (~95% to ~98%): "I have neighbors but not duplicates"
Zone 3 — Steep tail (last ~2-3%): "I'm alone in behavior space"
```

| Percentile | Value | Interpretation |
|---|---|---|
| 90th | 0.000 | Useless as eps — would only cluster exact duplicates |
| 95th | 0.000 | Same problem |
| **97th** | **0.872** | **The elbow — selected as eps** |
| 99th | 1.745 | Past the elbow — too lenient |

The fact that 95% of the dataset has k-distance ≈ 0 is itself a **finding**: the synthetic CERT workforce is extremely repetitive. Most user-days are exact duplicates of many other user-days. This made implementing an automatic fallback necessary — the code walks forward through percentiles until finding the first non-zero candidate.


## 7. DBSCAN vs K-Means Results

### Quantitative summary

```
Sample size:          100,000 user-days
DBSCAN parameters:    eps = 0.872, min_samples = 16
DBSCAN result:        86 clusters + 2,658 anomalies (2.7%)
K-Means baseline:     k = 2 (chosen by silhouette), silhouette = 0.816
PCA 2D variance:      71.3%
```

### The headline visualization

The side-by-side UMAP plot tells the central story:

- **DBSCAN (left panel):** 86 distinct purple/blue/green polka dots representing different shift patterns, plus a clear red splatter in the lower-center showing the 2,658 noise points clustered in a transitional zone between behaviors.
- **K-Means (right panel):** Every single point absorbed into one of two giant cyan clusters. The 86 actual behavioral patterns are invisible. The 2,658 anomalies are invisible.

Both panels show the same points in the same UMAP layout — only the color labels differ. The geometry is the same; the algorithm's output structure is dramatically different.


## 8. The Anomaly Profile — What Makes a User-Day Suspicious

Comparing Normal vs Anomaly user-days on each feature:

| Feature | Normal (mean) | Anomaly (mean) | Anomaly / Normal Ratio |
|---|---:|---:|---:|
| **n_after_hours** | 0.15 | 4.09 | **27.27×** |
| **n_weekend** | 0.05 | 0.37 | **7.40×** |
| **n_distinct_pcs** | 1.06 | 3.49 | **3.29×** |
| n_events | 2.39 | 7.69 | 3.22× |
| n_logons | 1.33 | 4.01 | 3.02× |
| hour_span | 9.46 | 14.72 | 1.56× |
| last_hour | 16.92 | 18.73 | 1.11× |
| first_hour | 7.47 | 4.01 | 0.54× (earlier) |

These ratios are the actual answer to "what does anomalous behavior look like?" An anomalous user-day is, on average:

- **27× more likely to contain after-hours activity**
- **7× more likely to involve weekend work**
- **3× more likely to span multiple machines**
- Started ~3.5 hours earlier and ended ~2 hours later than a normal day

This was achieved with **no labels, no rules, and no domain-specific configuration.** The clustering surfaced precisely the signals a human security analyst would manually call suspicious.

### Top extreme anomalies (sample)

| user | day | n_distinct_pcs | n_after_hours | first_hour | last_hour |
|---|---|---:|---:|---:|---:|
| DNS1768 | 2010-12-21 | 7 | 10 | 5 | 23 |
| JFG1049 | 2010-11-03 | 6 | 10 | 4 | 23 |
| CAM3050 | 2011-05-19 | 6 | 10 | 4 | 23 |
| PRH2431 | 2010-12-14 | 6 | 10 | 5 | 23 |
| EPI3052 | 2010-03-01 | 6 | 10 | 2 | 23 |

Each row is a real Zero Trust verification candidate — concrete (user, day) pairs that a Policy Decision Point would flag for step-up authentication or human review.


## 9. Conceptual Insights — Questions and Answers

### Q1: Why aggregate to user-days instead of clustering raw events?

**A:** Anomaly is a property of *patterns*, not of single events. A single logon at 3 AM is meaningless out of context. A user-day with 11 after-hours events across 7 PCs starting at 2 AM is unmistakably anomalous. The user-day aggregation is what turns event logs into behavioral fingerprints that can actually be clustered.

### Q2: Why does StandardScaler matter so much for DBSCAN?

**A:** DBSCAN uses Euclidean distance. Without scaling, a feature ranging 0–500 (`n_events`) would dominate one ranging 0–1 (`is_weekend`) by orders of magnitude — the smaller-scale feature becomes invisible to the algorithm. Standardization puts every feature on the same numeric footing so the distance metric reflects all 8 dimensions equally.

### Q3: What does the elbow in the k-distance plot represent?

**A:** It's the geometric boundary between "dense" and "sparse" regions in feature space. Points to the left of the elbow have neighbors close by; points to the right are isolated. Setting `eps` at the elbow's y-value tells DBSCAN: *"include in clusters anything denser than this threshold; mark anything sparser as noise."*

### Q4: Why use K-Means as a baseline if it can't represent anomalies?

**A:** That's exactly the point. Without a baseline, the report says *"I used DBSCAN and got 2.7% anomalies"* — a skeptical reader might ask *"Was a simpler method really insufficient?"* The K-Means contrast demonstrates that **standard clustering metrics (silhouette = 0.816 — apparently great!) don't reward the right thing for ZTN**. K-Means produces partition semantics; ZTN needs density semantics. The baseline shows *why* DBSCAN was necessary, not just *that* it was used.

### Q5: What does it mean that PCA and UMAP are computed but not fed into DBSCAN?

**A:** PCA and UMAP produce 2D projections suitable for visualization. But DBSCAN runs on the full 8D scaled feature space — that's where the actual density structure lives. The 2D projections are *labels overlaid on a canvas*, not inputs to clustering. This distinction matters because clustering on the 2D projection would lose information; we want DBSCAN to use all 8 features when computing distances.

### Q6: Does a user-day flagged as noise mean the user is malicious?

**A:** No. Noise means "behaviorally unusual" — which includes both insider threats and legitimate edge cases (someone genuinely working a weekend on deadline, an admin doing maintenance). The model is a **risk-score generator**, not a verdict. NIST SP 800-207's Policy Decision Point uses such signals as one input among many to decide whether to require step-up authentication, monitor more closely, or block access.

### Q7: Why 86 clusters and not 2 or 5?

**A:** Because the workforce isn't homogeneous. A real organization has many overlapping shift patterns: 8-to-5 office workers, early-morning operations staff, late-shift IT admins, executives who start at 7, support staff who span 9-to-9. Each pattern is its own dense region in behavior space. DBSCAN found 86 distinct ones automatically without being told to look for any specific number. A rule-based system saying "logon must be 8-10 AM" would falsely flag the 9.4% of the workforce in cluster 4 who legitimately work different hours.

### Q8: What would HDBSCAN give us beyond DBSCAN?

**A:** HDBSCAN finds clusters at *multiple density scales simultaneously*. DBSCAN uses one global `eps`, which means it can't simultaneously capture a dense 9-to-5 cohort *and* a sparser legitimate night-shift cohort — the night shift would either get clustered together with day-shift (eps too large) or be flagged as noise (eps too small). HDBSCAN handles this multi-density case natively. For real-world ZTN deployments where workforces have varying density patterns, HDBSCAN is the natural upgrade.


## 10. Findings & Their Implications for Zero Trust

**Finding 1: DBSCAN's noise label is the right primitive for Zero Trust.**
2.7% of user-days were flagged. K-Means absorbed those same points into the majority cluster, producing zero actionable signal despite a higher silhouette score. Silhouette rewards compactness, but compactness is not what ZTN needs — it needs a discrete "flag for verification" output, which only density-based methods produce natively.

**Finding 2: Behavioral data is dense-with-outliers, not clean-partition.**
The 86 DBSCAN clusters represent recurring shift patterns. The noise points are the off-pattern days within those patterns. K-Means would need k≈86 to match this granularity, and even then could not represent "this point belongs to no cluster." The mismatch between K-Means assumptions and ZTN data structure is fundamental.

**Finding 3: Class imbalance is fundamental, not a flaw.**
A 97/3 split between normal and anomaly is *expected* in real ZTN telemetry. Algorithms that require balance (most supervised classifiers) cannot operate here without synthetic oversampling. Density-based methods treat imbalance as the signal, not the noise.

**Finding 4: After-hours activity is the single strongest behavioral discriminator.**
The 27× ratio on `n_after_hours` is the dominant feature. This aligns with the broader insider-threat literature, where temporal anomaly is consistently the highest-recall single signal.

**Finding 5: Repetitive baseline is a synthetic dataset artifact.**
The fact that >95% of k-distances are zero indicates the CERT generator produces highly repetitive baseline behavior. Real workforces are noisier. A production deployment would expect a less extreme density gradient and would likely need HDBSCAN to discover clusters at multiple density scales.


## 11. Why This Matters Beyond the Assignment

The deeper insight from Task 2 isn't "DBSCAN beats K-Means." It's:

> **Different clustering algorithms optimize different objectives. The choice of algorithm should be driven by what the operational system needs to consume — not by which algorithm produces the prettiest standard metric.**

For Zero Trust:
- The output structure that matters is a **verification queue**.
- The metric that matters is **whether the noise points are behaviorally different from the normal points** — which is what the 27× / 7× / 3× ratios measure.
- The silhouette score K-Means optimizes is **operationally meaningless** here.

This methodological lesson — that algorithm choice should match output requirements, not optimize abstract metrics — extends well beyond clustering and well beyond ZTN.


## 12. Connection to Task 3

The 2,658 anomaly user-days in `anomalies_dbscan.csv` became the **data-scarce** seeds for Task 3 fine-tuning. The 97,342 normal user-days became the **data-rich** seeds. This natural imbalance — generated by clustering, not artificially introduced — was exactly the setup needed to demonstrate the link between training-data imbalance and model hallucination on rare classes.

Task 3 will show that the imbalance which DBSCAN naturally surfaces as "noise vs cluster" becomes, in the language model fine-tuning context, "data-rich vs data-scarce categories" — and the same data structure that helped DBSCAN succeed becomes the same data structure that makes language model fine-tuning fail without careful prompt engineering.

The two tasks are not separate experiments — they are two views of the same phenomenon: **rare events in cybersecurity behavioral data are valuable for detection precisely because they are rare, and that rarity is exactly what makes them hard to learn**.
