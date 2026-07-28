# LLMSA-MC: Detecting Missing-Check Bugs in OS Kernels with LLMs

Missing a security check is a class of semantic bugs in software programs where erroneous execution states are not validated. Missing-check bugs are particularly common in OS kernels because they frequently interact with external untrusted user space and hardware, and carry out error-prone computation. Missing-check bugs may cause a variety of critical security consequences, including permission bypasses, out-of-bound accesses, and system crashes.

LLMSA-MC detects missing-check bugs in the Linux kernel by combining static-analysis-derived candidate locations with LLM-based semantic validation. For each candidate location (a use of a security-sensitive variable that may lack a preceding check), the tool builds a chain-of-thought prompt from the candidate's source context — and, for inter-procedural cases, its caller function and callsite — and asks an LLM to judge whether the corresponding "critical variable" was actually validated before use. Both intra-procedural and inter-procedural candidates are supported, and results can be cross-checked against a CriX static-analysis baseline.

## How to use LLMSA-MC

### Prepare the candidate dataset

Candidate locations are pre-extracted (e.g. from a CriX static-analysis report) into `" ;; "`-delimited list files under `data/`:

- `mc.list` / `sc.list` — intra-procedural candidates (`mc` = suspected missing-check positives, `sc` = checked/negative samples)
- `mc_cross.list` / `sc_cross.list` — inter-procedural (cross-function) candidates

If you're starting from raw CriX/static-analyzer output instead of an existing `*_cross.list`, extract it into the classify lists with:

```bash
cd scripts

# Extract pattern_type=2 findings from a CriX report into mc_cross_1.xlsx
python process_mc_sc_cross_data.py --extract-cross
```

### Build the classify lists

Convert the raw candidate lists into the classified, context-enriched lists the LLM analysis step reads (source snippet, statement type, and — for cross candidates — caller/callsite).

```bash
cd scripts

# Inter-procedural: (re)generate mc_cross/sc_cross classify files
python process_mc_sc_cross_data.py --extract-cross-context
python process_mc_sc_cross_data.py --extract-sc-cross-context --input-file ../data/sc_cross.list --output-prefix sc_cross

# Intra-procedural: full mc/sc data-prep pipeline (classification, ground-truth matching, CriX comparison)
python process_mc_sc_data.py
```

### Configure the LLM client

The two analysis scripts construct their `OpenAI`-compatible client (base URL, API key, and an optional HTTP proxy) directly in the `if __name__ == '__main__':` block — edit that block to point at your own endpoint/key before running.

### Run the LLM analysis

```bash
cd scripts

# Inter-procedural candidates (mc_cross / sc_cross), prompt variants COT4-COT6
python llm_analysis_check_interprocedural.py --single-model gpt-4o --single-data-type mc_cross --single-prompt-type COT5

# Intra-procedural candidates (mc / sc), prompt variants COT0-COT3, with resume support
python llm_analysis_check_intraprocedural.py --single-model DeepSeek-V3 --single-data-type mc --single-prompt-type COT0

# Re-run specific samples across several models
python llm_analysis_check_interprocedural.py --models gpt-4o claude-sonnet-4-20250514 --data-types mc_cross --missing-ids 3 7 12

# Check progress / resume an interrupted intra-procedural run
python llm_analysis_check_intraprocedural.py --single-model DeepSeek-V3 --single-data-type mc --check-progress
python llm_analysis_check_intraprocedural.py --single-model DeepSeek-V3 --single-data-type mc --single-prompt-type COT0 --start-line 146 --previous-time 500
```

Run either script with `-h` for the full list of flags. Results are written per sample as `.txt` files, plus a summary CSV per (data type, prompt type, model) combination, under `data/ouput_results/`.

## Repository layout

```
data/
├── mc.list / sc.list                      intra-procedural candidates
├── mc_classify*.list / sc_classify*.list  classified + context, input to llm_analysis_check_intraprocedural.py
├── mc_cross.list / sc_cross.list          inter-procedural (cross-function) candidates
├── mc_cross_classify*.list / sc_cross_classify*.list  classified + context, input to llm_analysis_check_interprocedural.py
├── *_critical_variables.list              ground-truth critical variable per sample, for precision/recall evaluation
├── *_classify_function_labels.list        optional per-sample function-role labels used by richer prompt strategies (e.g. COT3)
├── crix-results/                          raw CriX static-analyzer reports at different confidence thresholds (0.15 / 0.20 / 0.25)
├── paper-results/                         curated ground-truth/paper artifacts used by process_mc_sc_data.py
├── kernel-code/                           Linux kernel source trees (not tracked in git; populate locally, e.g. linux-4.20-rc5)
└── ouput_results/                         LLM analysis output, created by the analysis scripts

scripts/
├── process_mc_sc_cross_data.py            builds the mc_cross_*/sc_cross_* classify lists from raw cross.list files
├── process_mc_sc_data.py                  end-to-end data prep for the intra-procedural mc/sc datasets and CriX baseline comparison
├── llm_analysis_check_interprocedural.py  LLM critical-variable check for the inter-procedural (cross-function) dataset
└── llm_analysis_check_intraprocedural.py  LLM critical-variable check for the intra-procedural dataset
```

All scripts use paths relative to `../data/...`, so run them from inside the `scripts/` directory.

## Requirements

- Python 3
- `pandas`, `openai`, `httpx`, `tqdm`
- `openpyxl` (only needed for the `.xlsx`-producing flags in `process_mc_sc_cross_data.py`)
- `myutil` — a local helper module imported by `process_mc_sc_data.py`; not included in this repository and must be supplied separately

## Flag reference

### `process_mc_sc_cross_data.py`

| Flag | Purpose |
|---|---|
| `--extract-cross` / `--extract-cross-2` / `--extract-cross-3` | extract `pattern_type=2` findings from `unchecked_locations_report.json` into `mc_cross_{1,2,3}.xlsx` |
| `--gen-exclude-list` | generate an exclude list from `mc_cross_1.xlsx` (used to avoid re-extracting the same findings into `mc_cross_2`) |
| `--extract-cross-context` | process `mc_cross.list` and generate classify results (default action if no flags given) |
| `--extract-sc-cross-context` | process `sc_cross.list` and generate classify results |
| `--input-file` | custom input file path (default depends on the flag above) |
| `--output-prefix` | output file prefix (default: `mc_cross` / `sc_cross`) |

### `llm_analysis_check_interprocedural.py` and `llm_analysis_check_intraprocedural.py`

| Flag | Purpose |
|---|---|
| `--models` / `--single-model` | which model(s) to run (e.g. `DeepSeek-V3`, `gpt-4o`, `claude-sonnet-4-20250514`, `gemini-2.5-pro`, `llama-3.3-70b`, `qwen3-coder-480b-a35b-instruct`) |
| `--data-types` / `--single-data-type` | `mc_cross`/`sc_cross` (interprocedural) or `mc`/`sc` (intraprocedural) |
| `--prompt-types` / `--single-prompt-type` | `COT4`-`COT6` (interprocedural) or `COT0`-`COT3` (intraprocedural) |
| `--missing-ids` | 1-based sample IDs to (re-)analyze |
| `--save-prompts` | *(interprocedural only)* also write the prompts sent to the LLM to `prompts.log` |
| `--self-consistency` | *(intraprocedural only)* run each sample 5 times and take the majority vote (forces prompt type to `COT0`) |
| `--start-line` | *(intraprocedural only)* resume from a specific 1-based sample number |
| `--previous-time` | *(intraprocedural only)* prior elapsed seconds to add to the total when resuming a run whose CSV wasn't saved |
| `--check-progress` | *(intraprocedural only)* print per-model/data-type/prompt-type progress and the next sample to resume from, then exit without analyzing |
