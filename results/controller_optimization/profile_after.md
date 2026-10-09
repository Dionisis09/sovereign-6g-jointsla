# Controller profile after

Seed 1, all 100 slots. cProfile perturbs runtime; these values attribute cost and are not budget measurements.
Exclusive function times and a selected-controller exclusive denominator avoid double-counting inclusive time.
Cumulative times retain child NumPy, sorting, copying and allocation costs. The pstats files retain all calls.

## SMALL

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| simulator.py:164:dispatch | 6417 | 52.663 | 359.097 | 15.74 |
| router.py:22:estimate | 45805 | 38.968 | 43.103 | 11.65 |
| optimized.py:66:_node_state | 9620 | 38.774 | 96.458 | 11.59 |
| optimized.py:74:nominal | 21752 | 27.587 | 124.045 | 8.25 |
| optimized.py:88:candidates | 8417 | 26.975 | 159.888 | 8.06 |
| simulator.py:105:worker | 87258 | 14.778 | 548.711 | 4.42 |
| optimized.py:57:worker | 87258 | 13.863 | 562.575 | 4.14 |
| simulator.py:61:get | 6264 | 11.307 | 60.950 | 3.38 |
| simulator.py:110:refresh_completed | 14681 | 11.241 | 13.789 | 3.36 |
| controller.py:8:deployment_quality | 2020 | 9.445 | 156.222 | 2.82 |
| policies.py:28:_fits | 4740 | 8.669 | 21.072 | 2.59 |
| optimized.py:109:snapshot | 200 | 8.613 | 42.846 | 2.57 |
| controller.py:30:joint_actions | 100 | 8.542 | 204.066 | 2.55 |
| optimized.py:141:dispatch | 6417 | 8.013 | 372.453 | 2.40 |
| simulator.py:41:flush | 12491 | 7.689 | 383.358 | 2.30 |

## MEDIUM

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| simulator.py:164:dispatch | 11290 | 104.590 | 701.048 | 13.68 |
| router.py:22:estimate | 88600 | 85.689 | 94.835 | 11.21 |
| optimized.py:74:nominal | 59529 | 84.881 | 278.710 | 11.10 |
| optimized.py:66:_node_state | 15594 | 77.633 | 193.807 | 10.15 |
| optimized.py:88:candidates | 15290 | 52.580 | 315.887 | 6.88 |
| policies.py:28:_fits | 23110 | 50.515 | 122.637 | 6.61 |
| simulator.py:105:worker | 153038 | 31.155 | 1152.780 | 4.07 |
| optimized.py:57:worker | 153038 | 29.080 | 1181.857 | 3.80 |
| optimized.py:109:snapshot | 200 | 23.881 | 136.790 | 3.12 |
| simulator.py:61:get | 10988 | 23.559 | 127.745 | 3.08 |
| controller.py:8:deployment_quality | 3934 | 23.279 | 346.687 | 3.04 |
| simulator.py:110:refresh_completed | 26278 | 22.161 | 26.998 | 2.90 |
| controller.py:30:joint_actions | 100 | 20.388 | 530.567 | 2.67 |
| policies.py:91:risk_score | 7449 | 17.490 | 24.519 | 2.29 |
| optimized.py:141:dispatch | 11290 | 16.168 | 730.295 | 2.11 |

## LARGE

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| optimized.py:74:nominal | 207492 | 274.544 | 788.510 | 14.27 |
| simulator.py:164:dispatch | 25639 | 257.349 | 1809.579 | 13.38 |
| optimized.py:66:_node_state | 38785 | 206.169 | 513.934 | 10.72 |
| router.py:22:estimate | 188339 | 194.870 | 215.038 | 10.13 |
| policies.py:28:_fits | 64360 | 137.692 | 330.479 | 7.16 |
| optimized.py:88:candidates | 33639 | 135.374 | 828.237 | 7.04 |
| simulator.py:105:worker | 344846 | 74.545 | 2767.862 | 3.88 |
| optimized.py:57:worker | 344846 | 68.555 | 2836.416 | 3.56 |
| simulator.py:61:get | 24751 | 59.196 | 326.846 | 3.08 |
| optimized.py:109:snapshot | 200 | 55.100 | 374.354 | 2.86 |
| simulator.py:110:refresh_completed | 58390 | 53.292 | 65.361 | 2.77 |
| controller.py:30:joint_actions | 100 | 42.413 | 1167.924 | 2.21 |
| controller.py:8:deployment_quality | 7227 | 41.293 | 719.692 | 2.15 |
| optimized.py:141:dispatch | 25639 | 40.718 | 1883.967 | 2.12 |
| simulator.py:41:flush | 49357 | 37.908 | 1937.984 | 1.97 |
