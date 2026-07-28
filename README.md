# LLMSA-MC: Detecting Missing-Check Bugs in OS Kernels with LLMs

Missing-check bugs are particularly common in OS kernels because they frequently interact with external untrusted user space and hardware, and carry out error-prone computation. Missing-check bugs may cause a variety of critical security consequences, including permission bypasses, out-of-bound accesses, and system crashes.

LLMSA-MC detects missing-check bugs in the Linux kernel by combining static analysis with LLM-based semantic validation. For each candidate location (a use of a security-sensitive variable that may lack a preceding check), the tool builds a chain-of-thought prompt from the candidate's source context — and, for inter-procedural cases, its caller function and callsite — and asks an LLM to judge whether the corresponding "critical variable" was actually validated before use. Both intra-procedural and inter-procedural candidates are supported.

## How to use LLMSA-MC

### Prepare the candidate dataset

Candidate locations are pre-extracted (e.g. from a CriX static-analysis report) into `" ;; "`-delimited list files under `data/`:

- `mc.list` / `sc.list` — intra-procedural candidates (`mc` = suspected missing-check positives, `sc` = checked/negative samples)
- `mc_cross.list` / `sc_cross.list` — inter-procedural (cross-function) candidates

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
