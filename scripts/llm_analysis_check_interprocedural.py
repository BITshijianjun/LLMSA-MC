import os
import threading
import csv
import argparse
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import time
import re
import logging
import httpx

write_lock = threading.Lock()
summary_lock = threading.Lock()
log_lock = threading.Lock()

summary_rows = []
prompt_logs = []
enable_prompt_log = False  # Global switch: whether prompt logging is enabled

# Unified prompt type definitions
dir = {0: 'COT4', 1: 'COT5', 2: 'COT6'}#, 3: 'COT7'}
# Unified data type definitions (including the new mc_cross format)
data_type = {0: "mc_cross", 1: "sc_cross"}

def extract_result(text):
    """
    Logic for extracting the result:
    1. First look for "Check Status:" lines (handles cases with multiple critical variables)
    2. Match by priority:
       - If any line has "has not been checked" -> return "Has not been checked"
       - If all lines have "has been checked" -> return "Has been checked"
    3. If no Check Status line is found, search the full text for negative/positive patterns
    """
    lower_text = text.lower()

    # Phase 1: find all "Check Status:" lines
    check_status_lines = []
    for line in text.split('\n'):
        if 'check status:' in line.lower():
            check_status_lines.append(line.lower())

    # If Check Status lines were found, process them by priority
    if check_status_lines:
        # Priority 1: check whether any line contains "has not been checked"
        for line in check_status_lines:
            if "has not been checked" in line:
                return "Has not been checked"

        # Priority 2: check whether any line contains "has been checked"
        for line in check_status_lines:
            if "has been checked" in line:
                return "Has been checked"

        # Priority 3: check for other phrasings of the result
        for line in check_status_lines:
            if "not" in line or "no" in line:
                return "Has not been checked"

        # Priority 4: default to "Has been checked" if a Check Status line was found but its content is inconclusive
        return "Has been checked"

    # Phase 2: if no Check Status line was found, search the full text
    # Priority: search negative patterns first (stricter)
    negative_patterns = [
        "has not been checked",
        "not properly validated",
        "not checked",
        "not validated",
    ]
    for pat in negative_patterns:
        if pat in lower_text:
            return "Has not been checked"

    # Then search positive patterns
    positive_patterns = [
        "has been checked",
        "properly validated",
        "properly checked",
        "validated",
        "checked",
        "proper validation",
        "necessary check",
    ]
    for pat in positive_patterns:
        if pat in lower_text:
            return "Has been checked"

    return "Unknown"


def write_output(output_dir, output_file, model, content, i, j):
    os.makedirs(output_dir, exist_ok=True)
    with write_lock:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(f"Model: {model}\n")
            file.write(content)
        print(f"Written: {output_file}")
    result = extract_result(content)
    with summary_lock:
        summary_rows.append([
            dir[j],  # Prompt type
            i + 1,  # Sample ID
            model,
            result,
            output_file
        ])
            
        
def analyze_output(output_dir, output_file, model, content, i, j):
    with open(output_file, "r", encoding="utf-8") as file:
            content = file.readlines()
            # print(content)
            result = extract_result('\n'.join(content))
            with summary_lock:
                summary_rows.append([
                    dir[j],  # Prompt type
                    i + 1,  # Sample ID
                    model,
                    result,
                    output_file
                ])

def log_prompt(model, sample_id, prompt_type, prompt_text, data_type_name):
    """Log the prompt sent to the LLM to a log file (if enabled)"""
    if not enable_prompt_log:
        return

    log_entry = {
        'model': model,
        'sample_id': sample_id,
        'prompt_type': prompt_type,
        'data_type': data_type_name,
        'prompt': prompt_text,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with log_lock:
        prompt_logs.append(log_entry)

def analyze_prompt(client, model, prompt, i, j, is_online, dt, data_type, prompt_type):
    output_dir = f"../data/ouput_results/{data_type[dt]}/{prompt_type[j]}_{model}"
    output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
    analyze_output(output_dir, output_file, model, "", i, j)

def process_prompt(client, model, prompt, i, j, is_online, dt, data_type, prompt_type):
    try:
        # Log the prompt
        log_prompt(model, i + 1, prompt_type[j], prompt, data_type[dt])

        output_dir = f"../data/ouput_results/{data_type[dt]}/{prompt_type[j]}_{model}"
        output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")

        selected_client = client
        
        # Use the chat.completions.create() API (other models)
        if is_online:
            completion = selected_client.chat.completions.create(
                model=model,
                web_search_options={},
                messages=[
                    {"role": "system", "content": "You are a static analysis expert specialized in Linux kernel security."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048
            )
        else:
            completion = selected_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a static analysis expert specialized in Linux kernel security."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_completion_tokens=2048,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                seed=123456,
            )

        write_output(output_dir, output_file, model, completion.choices[0].message.content, i, j)

    except Exception as e:
        print(f"[ERROR] Failed to process sample {i + 1} with model {model}: {str(e)}")
        output_dir = f"../data/ouput_results/{data_type[dt]}/{prompt_type[j]}_{model}"
        output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
        error_msg = f"Error: {str(e)}\nFailed to call model API. Please check:\n1. API key validity\n2. Network connection\n3. Model name correctness\n4. API endpoint accessibility"
        write_output(output_dir, output_file, model, error_msg, i, j)

def build_prompts(file, number, code, caller_function, callsite, code_context, type, function_label_info, parameter_annotation):
    return [
#naive explicit COT prompt (with full code contexts) 20260706
f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Analysis Instructions:
Step 1: Determine the analysis mode and identify the critical variable.
First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
- Inter-procedural analysis:
If both Caller Function and Callsite are provided, perform an inter-procedural analysis by jointly considering the targeted line, the corresponding callsite, and the provided source code context.
- Intra-procedural analysis:
If Caller Function or Callsite is unavailable, perform an intra-procedural analysis.
Use all available information together with the provided source code context to identify the critical variable.
A critical variable is the variable (e.g., a pointer, error code, or status flag) whose correctness or validity is required for the safe execution of the targeted line.
If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line.
Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
A valid safety check must satisfy all of the following requirements:
- The control-flow predicate must directly evaluate the critical variable identified in Step 1.
- The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
- The check introduces two distinct execution branches.
- One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
- The other branch continues normal execution.
A condition that only determines whether a statement using the critical variable is executed while evaluating a different variable or expression is not considered a safety check.
The analysis must be performed solely on the provided source code context.
Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code.
Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
Important:
Your analysis must be based only on the provided source code context.
Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Caller Function: {caller_function}
The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
Callsite: {callsite}
The corresponding function call statement in the caller. If unavailable, ignore this field.
Source Code Context: {code_context}
Required Response Format:
Step 1 Analysis:
- Analysis Mode:
- Critical Variable:
- Reason:
Step 2 Analysis:
- Validation:
- Supporting Evidence:
- Reason:
Final Result:
Critical Variable: <name or none>
Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
Evidence: <line(s) where the check occurs or explanation>
Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

## 20260707 (+STC with full_code_contexts)
f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Analysis Instructions:
Step 1: Determine the analysis mode and identify the critical variable.
First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
• Inter-procedural analysis:
If both Caller Function and Callsite are provided, If both Caller Function and Callsite are provided, perform an inter-procedural analysis by treating the mapped parameter and argument as the same critical variable and analyzing whether this critical variable is explicitly validated anywhere along the execution path before the targeted line is reached.
If Parameter Annotation is "Yes", identify the formal parameter used at the targeted line and determine its corresponding argument at the provided callsite. Treat them as representing the same critical variable across the function boundary, and report the corresponding callsite argument as the critical variable.
Otherwise, determine the critical variable directly from the targeted line according to its statement type using the same rules as the intra-procedural analysis.
For pointer dereference expressions:
- For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
- For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
• Intra-procedural analysis:
If Caller Function or Callsite is unavailable, perform an intra-procedural analysis.
Determine the critical variable according to the targeted line type:
- Function call with return value:
If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
- Function call without return value:
Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
- Array operation:
Treat the array index variable as the critical variable.
- Other types:
Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line.
Step 2: Using the critical variable identified in Step 1, determine whether the critical variable has been explicitly validated before the execution reaches the targeted line.
A valid safety check must satisfy all of the following requirements:
- The control-flow predicate must directly evaluate the critical variable itself identified in Step 1.
- The condition must determine whether the critical variable itself is safe to use (e.g., non-NULL, non-error, within valid bounds, or otherwise valid for the targeted operation).
- The check introduces two distinct execution branches.
- One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
- The other branch continues normal execution.
A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
The analysis must be performed solely on the provided code context, considering all relevant control-flow information while following the above definition of a safety check.
Every reported safety check must be directly supported by explicit control-flow evidence in the provided code context.
Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
Important:
Your analysis must be based only on the provided source code context.
Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Parameter Annotation: {parameter_annotation}
Indicates whether the identified critical variable is a formal parameter of the enclosing function.
Caller Function: {caller_function}
The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
Callsite: {callsite}
The corresponding function call statement in the caller. If unavailable, ignore this field.
Source Code Context: {code_context}
Required Response Format:
Step 1 Analysis:
- Analysis Mode:
- Critical Variable:
- Reason:
Step 2 Analysis:
- Validation:
- Supporting Evidence:
- Reason:
Final Result:
Critical Variable: <name or none>
Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
Evidence: <line(s) where the check occurs or explanation>
Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

# ## 20260707 (+STC+PCCE with classify_code_contexts)
f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Analysis Instructions:
Step 1: Determine the analysis mode and identify the critical variable.
First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
• Inter-procedural analysis:
If both Caller Function and Callsite are provided, If both Caller Function and Callsite are provided, perform an inter-procedural analysis by treating the mapped parameter and argument as the same critical variable and analyzing whether this critical variable is explicitly validated anywhere along the execution path before the targeted line is reached.
If Parameter Annotation is "Yes", identify the formal parameter used at the targeted line and determine its corresponding argument at the provided callsite. Treat them as representing the same critical variable across the function boundary, and report the corresponding callsite argument as the critical variable.
Otherwise, determine the critical variable directly from the targeted line according to its statement type using the same rules as the intra-procedural analysis.
For pointer dereference expressions:
- For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
- For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
• Intra-procedural analysis:
If Caller Function or Callsite is unavailable, perform an intra-procedural analysis.
Determine the critical variable according to the targeted line type:
- Function call with return value:
If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
- Function call without return value:
Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
- Array operation:
Treat the array index variable as the critical variable.
- Other types:
Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line.
Step 2: Using the critical variable identified in Step 1, determine whether the critical variable has been explicitly validated before the execution reaches the targeted line.
A valid safety check must satisfy all of the following requirements:
- The control-flow predicate must directly validate the critical variable itself identified in Step 1.
- The condition must determine whether the critical variable itself is safe to use (e.g., non-NULL, non-error, within valid bounds, or otherwise valid for the targeted operation).
- The check introduces two distinct execution branches.
- One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
- The other branch continues normal execution.
A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
The analysis must be performed solely on the provided code context, considering all relevant control-flow information while following the above definition of a safety check.
Every reported safety check must be directly supported by explicit control-flow evidence in the provided code context.
Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
Important:
Your analysis must be based only on the provided source code context.
Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Parameter Annotation: {parameter_annotation}
Indicates whether the identified critical variable is a formal parameter of the enclosing function.
Caller Function: {caller_function}
The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
Callsite: {callsite}
The corresponding function call statement in the caller. If unavailable, ignore this field.
Source Code Context: {code_context}
Required Response Format:
Step 1 Analysis:
- Analysis Mode:
- Critical Variable:
- Reason:
Step 2 Analysis:
- Validation:
- Supporting Evidence:
- Reason:
Final Result:
Critical Variable: <name or none>
Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
Evidence: <line(s) where the check occurs or explanation>
Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

]


def parse_line(line):
    """
    Parse a line of data, supporting the file formats of different data types

    For the mc_cross data type, use the new format (8 fields):
        file_path ;; line_no ;; targeted_line_code ;; caller_function ;; callsite ;; context ;; type ;; parameter_annotation

    For other data types, support the standard format (5 fields):
        file_path ;; line_no ;; line_code ;; context ;; type
    """
    parts = line.strip().split(" ;; ")
    start_idx = 0

    # Extract the basic fields
    abs_path = parts[start_idx].strip()
    rel_path = abs_path.replace("../data/kernel-code/", "")
    file_path = rel_path

    line_no = parts[start_idx + 1].strip() if len(parts) > start_idx + 1 else ""

    # Check whether this is the new format (8 fields) or the old format (5 fields)
    if len(parts) >= 8:
        # New mc_cross format
        targeted_line_code = parts[start_idx + 2].strip() if len(parts) > start_idx + 2 else ""
        caller_function = parts[start_idx + 3].strip() if len(parts) > start_idx + 3 else ""
        callsite_code = parts[start_idx + 4].strip() if len(parts) > start_idx + 4 else ""
        context_code = parts[start_idx + 5].strip() if len(parts) > start_idx + 5 else ""
        raw_type = parts[start_idx + 6].strip() if len(parts) > start_idx + 6 else ""
        parameter_annotation = parts[start_idx + 7].strip() if len(parts) > start_idx + 7 else "No"
        return file_path, line_no, targeted_line_code, caller_function, callsite_code, context_code, raw_type, parameter_annotation
    else:
        # Old format (compatible with other data types)
        line_code = parts[start_idx + 2].strip() if len(parts) > start_idx + 2 else ""
        context_code = parts[start_idx + 3].strip() if len(parts) > start_idx + 3 else ""
        raw_type = parts[start_idx + 4].strip() if len(parts) > start_idx + 4 else ""
        parameter_annotation = parts[start_idx + 5].strip() if len(parts) > start_idx + 5 else "No"
        # Return-format compatibility: return 8 values, with the trailing ones left empty
        return file_path, line_no, line_code, "", "", context_code, raw_type, parameter_annotation


def is_responses_api_model(model):
    """Check whether the model uses the responses.create() API"""
    responses_models = ['DeepSeek-R1', 'Qwen3-Coder']
    return any(model_name in model for model_name in responses_models)

def test_api_connection(client, model):
    """Test whether the connection to the API is working"""
    try:
        if is_responses_api_model(model):
            # Use the responses.create() API
            response = client.responses.create(
                model=model,
                input="Say 'Hello' briefly",
                text={"verbosity": "low"}
            )
        else:
            # Use the chat.completions.create() API
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Say 'Hello' briefly"}
                ],
                max_completion_tokens=10,
                temperature=0,
            )
        return True
    except Exception as e:
        print(f"[CRITICAL] API connection test FAILED for model {model}: {str(e)}")
        print(repr(e))
        return False

def save_prompt_log(data_type_name, prompt_type_name, model_name):
    """Save the collected prompt logs to a file (if enabled)"""
    if not enable_prompt_log or not prompt_logs:
        return

    log_dir = f"../data/ouput_results/{data_type_name}/{prompt_type_name}_{model_name}"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "prompts.log")

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("="*80 + "\n")
        f.write(f"LLM Analysis Prompt Log\n")
        f.write(f"Model: {model_name}\n")
        f.write(f"Data Type: {data_type_name}\n")
        f.write(f"Prompt Type: {prompt_type_name}\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

        for entry in prompt_logs:
            f.write(f"{'='*80}\n")
            f.write(f"Sample ID: {entry['sample_id']}\n")
            f.write(f"Model: {entry['model']}\n")
            f.write(f"Timestamp: {entry['timestamp']}\n")
            f.write(f"{'='*80}\n")
            f.write(f"{entry['prompt']}\n")
            f.write("\n" + "-"*80 + "\n\n")

    print(f"✓ Prompt log saved to {log_file}")

def llm_analysis(client, model_list, is_online_model, data_type, prompt_type, dt=0, j=0, missing_ids=None):
    
    """
    Main function for analyzing prompts
    Parameters:
    - dt: data type index (0:mc, 1:sc, 2:bug_list_0.15, 3:mc_macro)
    - j: prompt type index (0:COT0, 1:COT1, 2:COT2, 3:COT3, 4:Few-Shots, 5:Few-Shots+LLMSA-MC)
    - missing_ids: list of sample IDs to analyze (1-based, e.g., [1, 2, 3, 5]). If None, analyze all samples
    """

    # Determine the configuration strategy based on the prompt_type index
    # COT0: naive prompt: type="", function_label_info="", file: classify_full_contexts.list
    # COT1: +STC prompt: type set, function_label_info="", file: classify_full_contexts.list
    # COT2: +STC+PCCE prompt: type set, function_label_info="", file: classify.list
    # COT3: +STC+PCCE+FLG prompt: type set, function_label_info set, file: classify.list
    # Few-Shots: basic few-shot learning examples, uses the COT0 strategy
    # Few-Shots1: enhanced few-shot learning (with function labels), uses the COT3 strategy

    cot_strategy = {
        0: {'use_type': False, 'use_function_labels': False, 'use_full_contexts': True},   # COT0
        1: {'use_type': True,  'use_function_labels': False, 'use_full_contexts': True},   # COT1
        2: {'use_type': True,  'use_function_labels': False, 'use_full_contexts': False},  # COT2
        3: {'use_type': True,  'use_function_labels': True,  'use_full_contexts': False},  # COT3
        4: {'use_type': False, 'use_function_labels': False, 'use_full_contexts': True},   # Few-Shots (same as COT0)
        5: {'use_type': True,  'use_function_labels': True, 'use_full_contexts': False},  # Few-Shots1 (same as COT3)
    }

    strategy = cot_strategy.get(j, {'use_type': False, 'use_function_labels': False, 'use_full_contexts': True})
    use_type = strategy['use_type']
    use_function_labels = strategy['use_function_labels']
    use_full_contexts = strategy['use_full_contexts']

    # Determine which file to read
    if use_full_contexts:
        list_file = f"../data/{data_type[dt]}_classify_full_contexts.list"
    else:
        list_file = f"../data/{data_type[dt]}_classify.list"

    # If function_labels are needed, read them from the corresponding file
    function_labels = {}
    if use_function_labels:
        labels_file = f"../data/{data_type[dt]}_classify_function_labels.list"
        try:
            with open(labels_file, 'r', encoding='utf-8') as file:
                for line in file.readlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(':')
                    if len(parts) == 2:
                        seq_num = int(parts[0])
                        label = parts[1]
                        function_labels[seq_num] = label
        except FileNotFoundError:
            pass

    start_time = time.time()

    # If missing_ids is specified, only analyze those samples (convert 1-based to 0-based)
    sample_indices = None
    if missing_ids:
        sample_indices = set(id - 1 for id in missing_ids)  # Convert to 0-based indices

    # Set the concurrency level: use max_workers=1 (sequential) when analyzing missing_ids, otherwise max_workers=8
    max_workers = 1 if missing_ids else 8
    max_workers = 1 if data_type[dt] == "mc_macro" else max_workers  # The mc_macro dataset also runs sequentially

    try:
        if not os.path.exists(list_file):
            return None

        with open(list_file, "r", encoding='utf-8') as f:
            lines = f.readlines()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(len(lines)):
                # If sample IDs are specified, only process those samples
                if sample_indices is not None and i not in sample_indices:
                    continue

                try:
                    # Use the unified parsing function
                    parse_result = parse_line(lines[i])

                    # Determine whether it's the new or old format based on the length of the return value
                    if len(parse_result) == 8:
                        file_path, line_no, targeted_line_code, caller_function, callsite_code, context_code, raw_type, parameter_annotation = parse_result
                    else:
                        file_path, line_no, line_code, context_code, raw_type, parameter_annotation = parse_result[:6]
                        targeted_line_code = line_code
                        caller_function = ""
                        callsite_code = ""

                    # Decide whether to use type based on the strategy
                    if use_type:
                        if raw_type == 'Returning Function Call' or raw_type == 'Function Call with Assignment':
                            line_type = 'Function call with return value'
                        elif raw_type == 'Void Function Call' or raw_type == 'Function Call':
                            line_type = 'Function call without return value'
                        elif raw_type == 'Array Access' or raw_type == 'Array/Pointer Access':
                            line_type = 'Array Operation'
                        elif raw_type == 'Variable Declaration' or raw_type == 'Variable Declaration with Assignment':
                            line_type = 'Other'
                        elif raw_type == 'Assignment Statement' or raw_type == 'Function Definition':
                            line_type = 'Other'
                        else:
                            line_type = raw_type
                    else:
                        line_type = ""

                    # Decide whether to use function_label_info based on the strategy
                    function_label_info = ""
                    if use_function_labels:
                        seq_num = i + 1  # Convert the 0-based index to a 1-based sequence number
                        if seq_num in function_labels:
                            label_value = function_labels[seq_num]
                            # Only use it when the label value is not '0'
                            if label_value != '0':
                                function_label_info = label_value

                    # Escape variables containing curly braces to avoid .format() errors
                    # build_prompts requires: file, number, code, caller_function, callsite, code_context, type, function_label_info, parameter_annotation
                    prompt = build_prompts(file_path, line_no, targeted_line_code, caller_function, callsite_code, context_code, line_type, function_label_info, parameter_annotation)[j]

                    for model in model_list:
                        future = executor.submit(
                            process_prompt,
                            client,
                            model,
                            prompt,
                            i,
                            j,
                            is_online_model,
                            dt,
                            data_type,
                            prompt_type
                        )
                        futures.append((i + 1, model, future))
                except Exception as e:
                    print(f"[Error] Failed to prepare sample {i + 1}: {str(e)}")
                    continue

            # Wait for all tasks to complete
            for sample_id, model, future in futures:
                try:
                    future.result(timeout=300)  # Per-task timeout of 5 minutes
                except Exception as e:
                    pass

    except FileNotFoundError:
        return None
    except Exception as e:
        return None

    end_time = time.time()
    elapsed_time = end_time - start_time
    return elapsed_time
                    

            


def create_parser():
    parser = argparse.ArgumentParser(description='LLM Analysis Tool')
    parser.add_argument('--models', nargs='+', default=None,
                        help='List of models to analyze (default: all)')
    parser.add_argument('--data-types', nargs='+', default=None,
                        help='Data types to process (default: all)')
    parser.add_argument('--prompt-types', nargs='+', default=None,
                        help='Prompt types to use (default: all)')
    parser.add_argument('--single-model', type=str, default=None,
                        help='Single model for quick debug')
    parser.add_argument('--single-data-type', type=str, default=None,
                        help='Single data type for quick debug')
    parser.add_argument('--single-prompt-type', type=str, default=None,
                        help='Single prompt type for quick debug')
    parser.add_argument('--missing-ids', nargs='+', type=int, default=None,
                        help='Sample IDs to analyze (1-based, e.g., --missing-ids 1 2 3 5 6)')
    parser.add_argument('--save-prompts', action='store_true', default=False,
                        help='Enable saving LLM prompts to log files (default: disabled)')
    return parser.parse_args()


if __name__ == '__main__':
    args = create_parser()

    # Set the global logging switch
    globals()['enable_prompt_log'] = args.save_prompts

    client = OpenAI(
        base_url="your-api-base-url-here",  # Replace with your actual API base URL
        api_key="your-api-key-here"  # Replace with your actual API key,
    )

    # Model online-status mapping (whether web_search_options is needed)
    model_online_status = {
        'DeepSeek-V3': False,
        'qwen3-coder-480b-a35b-instruct': False,
        'llama-3.3-70b': False,
        'gpt-4o': False,
        'claude-sonnet-4-20250514': False,
        'gemini-2.5-pro': False,
    }

    # Process command-line arguments - supports single-item debugging or batch processing
    if args.single_model:
        model_list = [args.single_model]
    elif args.models:
        model_list = args.models
    else:
        model_list = list(model_online_status.keys())

    if args.single_data_type:
        data_type_indices = [k for k, v in data_type.items() if v == args.single_data_type]
    elif args.data_types:
        data_type_indices = [k for k, v in data_type.items() if v in args.data_types]
    else:
        data_type_indices = list(data_type.keys())

    if args.single_prompt_type:
        prompt_type_indices = [k for k, v in dir.items() if v == args.single_prompt_type]
    elif args.prompt_types:
        prompt_type_indices = [k for k, v in dir.items() if v in args.prompt_types]
    else:
        prompt_type_indices = list(dir.keys())

    print(f"Models: {model_list}")
    print(f"Data types: {[data_type[i] for i in data_type_indices]}")
    print(f"Prompt types: {[dir[i] for i in prompt_type_indices]}")
    if args.missing_ids:
        print(f"Missing sample IDs to analyze: {args.missing_ids}")
    print()

    # Test the API connection before starting the analysis
    api_ok = False
    for model in model_list:
        if test_api_connection(client, model):
            api_ok = True
            break

    if not api_ok:
        print("[CRITICAL] API connection failed!")
        exit(1)

    # Iterate over all combinations to analyze
    for dt in data_type_indices:
        for j in prompt_type_indices:
            for model in model_list:
                # Determine whether the model is online
                is_online_model = model_online_status.get(model, False)

                summary_rows.clear()

                # Call llm_analysis to perform the analysis
                elapsed_time = llm_analysis(client, [model], is_online_model, data_type, dir, dt=dt, j=j, missing_ids=args.missing_ids)

                # Generate a CSV result for each combination
                output_csv = f"../data/ouput_results/{data_type[dt]}_{dir[j]}_{model}_result.csv"
                os.makedirs(os.path.dirname(output_csv), exist_ok=True)

                # If this is supplementary data from a missing_ids analysis, append to the original file
                if args.missing_ids:
                    # Read the contents of the original file (excluding the trailing time-summary row)
                    existing_rows = []
                    total_time = elapsed_time

                    if os.path.exists(output_csv):
                        with open(output_csv, "r", newline='', encoding="utf-8") as f:
                            reader = csv.reader(f)
                            for i, row in enumerate(reader):
                                if i == 0:  # Skip the header row
                                    continue
                                # Skip the trailing time-summary row (usually contains "Total analysis time")
                                if row and len(row) > 0 and "Total analysis time" in str(row[0]):
                                    # Extract the previous analysis time from this row
                                    time_str = str(row[0])
                                    # Try to extract the numeric time value
                                    import re
                                    match = re.search(r'(\d+\.\d+)', time_str)
                                    if match:
                                        try:
                                            total_time += float(match.group(1))
                                        except:
                                            pass
                                else:
                                    existing_rows.append(row)

                    # Write the original rows + new rows
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(existing_rows)
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV updated to {output_csv}")
                else:
                    # Normal case: create a new file
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV written to {output_csv}")

                # Save the prompt log
                save_prompt_log(data_type[dt], dir[j], model)
                prompt_logs.clear()  # Clear the log list before moving to the next combination