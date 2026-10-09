# JointSLA — Οργανωμένος φάκελος project

Κεντρικό σημείο για παρουσίαση, μαθηματική μεθοδολογία, paper και ολοκληρωμένα αποτελέσματα. Ο κώδικας και τα πρωτότυπα frozen δεδομένα παραμένουν στις υπάρχουσες διαδρομές του repository, ώστε να συνεχίζουν να λειτουργούν dashboard, scripts και hash verification.

## Ξεκίνα από εδώ

| Τι χρειάζεσαι | Αρχείο |
|---|---|
| Κύρια παρουσίαση όλου του project · 107 διαφάνειες | [JointSLA Complete Presentation](02_Presentations/JointSLA_Complete_Presentation.pptx) |
| Scaler και router · συναρτήσεις, προέλευση παραμέτρων και παραδείγματα στα ελληνικά | [Μαθηματικό Word](01_Methodology/JointSLA_Mathematical_Methodology.docx) |
| Κύρια τεχνική αναφορά με τελική Kubernetes αξιολόγηση | [Technical Report](03_Reports/JointSLA_Technical_Report.docx) |
| Κύριο conference paper draft | [Paper](04_Paper/JointSLA_Paper.docx) |
| Συμπληρωματική πλήρης αναφορά simulation | [Word](03_Reports/JointSLA_Simulation_Report.docx) · [PDF](03_Reports/JointSLA_Simulation_Report.pdf) |

Η παρουσίαση των 107 διαφανειών είναι η πληρέστερη παρουσίαση και περιλαμβάνει την ερευνητική διαδρομή, αρχιτεκτονική, συναρτήσεις, simulation και Kubernetes αποτελέσματα, graphs, συμπεράσματα, περιορισμούς και MaaS request pipeline με πραγματικά screenshots των dashboards (διαφάνειες 55–61). Δεν υπάρχουν εναλλακτικές παλιότερες παρουσιάσεις σε αυτόν τον φάκελο. Η μαθηματική, simulation και infrastructure τεκμηρίωση είναι συμπληρωματικά θέματα, όχι ανταγωνιστικές εκδόσεις της κύριας αναφοράς.

## Δομή αυτού του φακέλου

```text
JointSLA/
  README.md                Οδηγός και σύνδεσμοι
  ARTIFACT_MANIFEST.json    Προέλευση αρχείων και SHA-256 hashes
  01_Methodology/          Μαθηματικό Word για scaler / router
  02_Presentations/        Μία πλήρης παρουσίαση
  03_Reports/              Τελική Kubernetes αναφορά και infrastructure reports
  04_Paper/                Conference draft και SOVEREIGN mapping
  05_Figures/              7 τελικά Kubernetes figures σε PNG και vector PDF
  06_Tables/               Τελικοί πίνακες CSV και canonical_results.json
  08_Dashboard_Screenshots/ MaaS, research dashboard και live Grafana captures
```

Οι φάκελοι περιέχουν τα επιλεγμένα κύρια αρχεία με καθαρά ονόματα χωρίς version suffix, για εύκολη ανάγνωση και αποστολή. Δεν αποτελούν νέο πείραμα ούτε αντικαθιστούν τα frozen πρωτότυπα. Το manifest καταγράφει την ακριβή αρχική διαδρομή και το hash κάθε αντιγράφου. Αν αλλάξει στο μέλλον ένα πρωτότυπο, αυτό το snapshot χρειάζεται ρητή ανανέωση. Οι επιστημονικές αναφορές σε v1/v2 μέσα στο περιεχόμενο διατηρούνται, επειδή προσδιορίζουν διαφορετικές μεθόδους και experiments.

Τα αρχεία Markdown αναφορών κρατούν το αρχικό περιεχόμενο και τους αρχικούς σχετικούς συνδέσμους. Για να λειτουργούν αυτοί οι σύνδεσμοι, άνοιξε τα πρωτότυπα που παρατίθενται παρακάτω. Τα Word και PowerPoint του snapshot είναι αυτοτελή αρχεία.

## Πού βρίσκεται η υλοποίηση

| Περιοχή | Πρωτότυπος φάκελος / οδηγός |
|---|---|
| Static placement και dynamic simulation | [placement_experiment](../placement_experiment/README.md), [dynamic_placement](../dynamic_placement/README.md) |
| JointSLA routing και simulator v2 | [joint_routing](../joint_routing/README.md), [joint_sla_v2](../joint_sla_v2/README.md) |
| Hardware profiling και pressure experiments | [hardware_grounded](../hardware_grounded/README.md), [hardware_pressure](../hardware_pressure/README.md) |
| Statistical experiments και comparator | [paper_evaluation](../paper_evaluation/README.md), [strong_baseline](../strong_baseline/README.md) |
| Scalability και controller optimization | [scalability](../scalability/README.md), [controller_optimization](../controller_optimization/README.md) |
| Real PyTorch inference, Docker και gateway | [prototype](../prototype/README.md) |
| Kubernetes, deployment, probes, draining, recovery | [prototype/kubernetes](../prototype/kubernetes/README.md) |
| Dashboard και MaaS demo | [dashboard](../dashboard/README.md) |
| Tests | [tests](../tests/) |
| Όλα τα αρχικά πειραματικά outputs | [results](../results/) |

## Dashboard / πραγματικό inference

- [Research dashboard](http://127.0.0.1:8501/)
- [Kubernetes comparison v2](http://127.0.0.1:8501/?view=kubernetes-v2)
- [AI Inference / MaaS Demo](http://127.0.0.1:8501/?view=maas): ανέβασε εικόνα και πάτησε **Run real inference**.
- [Live Grafana](http://127.0.0.1:3001/d/jointsla-runtime)

Από τη ρίζα του repository:

```powershell
.venv\Scripts\python.exe run_dashboard.py
```

Το MaaS demo και το Grafana χρειάζονται Docker και το local Kubernetes prototype. Το υπάρχον deployment command είναι:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File prototype/kubernetes/deploy.ps1 -SkipBuild
```

Το `-SkipBuild` προϋποθέτει τις υπάρχουσες application images. Για αρχική εγκατάσταση δες τον [οδηγό Kubernetes](../prototype/kubernetes/README.md). Δεν χρειάζεται να ξανατρέξεις τα ερευνητικά experiments για να ανοίξεις τις τελικές αναφορές.

## Πρωτότυπα αποτελέσματα και αναφορές

- [Frozen Kubernetes publication package](../docs/jointsla_kubernetes_v2_final/README.md) — authoritative tables, figures, methodology, manifests και verification scripts.
- [Final technical report με λειτουργικούς σχετικούς συνδέσμους](../docs/jointsla_kubernetes_v2_final/JointSLA_Final_Technical_Report.md).
- [Infrastructure validation](../INFRASTRUCTURE_VALIDATION.md).
- [Unified historical infrastructure report](../JOINTSLA_FINAL_REPORT.md).
- [Checkpoint τελικών αποτελεσμάτων](../docs/checkpoints/2026-10-09_kubernetes-v2_final.md).
- [Held-out simulator report](../docs/jointsla_v2_report/JointSLA_v2_Experimental_Report.docx).

Οι simulation και Kubernetes αξιολογήσεις είναι διαφορετικά experiments. Γι' αυτό η κύρια τεχνική αναφορά συνοδεύεται από μία ειδική simulation αναφορά, χωρίς ανάμειξη των μετρήσεών τους.

## Τι παραμένει σταθερό

Το τελικό Kubernetes comparison δείχνει **49,89% SLA failures έναντι 61,43% reactive**, με **58,84% περισσότερα target replica-seconds**. Δεν ισχυριζόμαστε καλύτερη resource efficiency. Οι τιμές 38,83% και 47,27% αφορούν διαφορετικά παλαιότερα runs. Οι συναρτήσεις και οι σταθερές του scaler/router τεκμηριώνονται ως design / engineering choices, χωρίς ισχυρισμό ότι προέκυψαν από optimization.

Οι προσωρινές μετρήσεις του MaaS demo δεν ενσωματώνονται στα frozen research results.

## Screenshots και σημερινό demo

[Έξι dashboard screenshots και provenance](08_Dashboard_Screenshots/README.md) ενσωματώνονται στην κύρια παρουσίαση. Το πραγματικό image request επέστρεψε HTTP 200, 98,1 ms client latency και SLA MET για deadline 200 ms. Αποτελεί λειτουργικό παράδειγμα· δεν προστίθεται στο frozen benchmark ούτε αποδεικνύει model accuracy ή γενική SLA εγγύηση.
