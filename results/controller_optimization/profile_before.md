# Controller profile before

Seed 1, all 100 slots. cProfile perturbs runtime; these values attribute cost and are not budget measurements.
Exclusive function times and a selected-controller exclusive denominator avoid double-counting inclusive time.
Cumulative times retain child NumPy, sorting, copying and allocation costs. The pstats files retain all calls.

## SMALL

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| simulator.py:126:nominal | 21752 | 159.794 | 368.391 | 35.69 |
| simulator.py:164:dispatch | 6417 | 55.931 | 459.569 | 12.49 |
| router.py:22:estimate | 45805 | 40.047 | 44.493 | 8.94 |
| simulator.py:143:candidates | 8417 | 35.082 | 280.521 | 7.84 |
| simulator.py:25:items | 13911 | 22.306 | 40.205 | 4.98 |
| simulator.py:105:worker | 87258 | 15.280 | 572.532 | 3.41 |
| simulator.py:61:get | 6264 | 12.191 | 68.427 | 2.72 |
| simulator.py:110:refresh_completed | 14681 | 11.866 | 14.370 | 2.65 |
| controller.py:8:deployment_quality | 2020 | 9.470 | 157.979 | 2.12 |
| policies.py:28:_fits | 4740 | 8.768 | 20.566 | 1.96 |
| controller.py:30:joint_actions | 100 | 8.636 | 205.344 | 1.93 |
| simulator.py:41:flush | 12491 | 8.170 | 486.075 | 1.82 |
| simulator.py:34:put | 6227 | 7.717 | 482.478 | 1.72 |
| policies.py:91:risk_score | 3825 | 7.706 | 11.086 | 1.72 |
| router.py:43:choose | 12834 | 6.671 | 49.091 | 1.49 |

## MEDIUM

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| simulator.py:126:nominal | 59529 | 403.430 | 936.891 | 40.53 |
| simulator.py:164:dispatch | 11290 | 97.886 | 769.082 | 9.83 |
| router.py:22:estimate | 88600 | 73.508 | 81.699 | 7.38 |
| simulator.py:143:candidates | 15290 | 68.440 | 475.072 | 6.88 |
| simulator.py:25:items | 28114 | 68.292 | 121.519 | 6.86 |
| policies.py:28:_fits | 23110 | 39.996 | 91.960 | 4.02 |
| simulator.py:105:worker | 153010 | 26.666 | 1013.701 | 2.68 |
| simulator.py:61:get | 10988 | 21.538 | 122.162 | 2.16 |
| simulator.py:110:refresh_completed | 26278 | 20.529 | 25.032 | 2.06 |
| controller.py:8:deployment_quality | 3934 | 19.934 | 304.822 | 2.00 |
| simulator.py:199:snapshot | 200 | 18.789 | 800.350 | 1.89 |
| controller.py:30:joint_actions | 100 | 18.348 | 448.490 | 1.84 |
| simulator.py:32:<lambda> | 298971 | 16.587 | 16.587 | 1.67 |
| simulator.py:41:flush | 21907 | 14.346 | 814.313 | 1.44 |
| policies.py:91:risk_score | 7449 | 14.057 | 20.351 | 1.41 |

## LARGE

| Function | Calls | Exclusive ms | Cumulative ms | Controller % |
|---|---:|---:|---:|---:|
| simulator.py:126:nominal | 207492 | 1369.042 | 3147.233 | 48.59 |
| simulator.py:25:items | 55720 | 238.260 | 318.843 | 8.46 |
| simulator.py:164:dispatch | 25639 | 221.114 | 1874.768 | 7.85 |
| simulator.py:143:candidates | 33639 | 205.082 | 1179.453 | 7.28 |
| router.py:22:estimate | 188339 | 160.272 | 177.571 | 5.69 |
| policies.py:28:_fits | 64360 | 109.015 | 249.536 | 3.87 |
| simulator.py:105:worker | 344846 | 60.640 | 2304.058 | 2.15 |
| simulator.py:61:get | 24751 | 49.149 | 296.701 | 1.74 |
| simulator.py:199:snapshot | 200 | 46.314 | 2815.862 | 1.64 |
| simulator.py:110:refresh_completed | 58390 | 46.118 | 56.773 | 1.64 |
| controller.py:30:joint_actions | 100 | 36.165 | 971.372 | 1.28 |
| controller.py:8:deployment_quality | 7227 | 35.072 | 625.724 | 1.24 |
| simulator.py:41:flush | 49357 | 32.453 | 1978.479 | 1.15 |
| simulator.py:34:put | 24606 | 30.551 | 1944.246 | 1.08 |
| router.py:43:choose | 51278 | 26.275 | 194.770 | 0.93 |
