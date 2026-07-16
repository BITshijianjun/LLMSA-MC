# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os
import sys
import threading
import csv
import argparse
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import time
import re
import httpx

write_lock = threading.Lock()
summary_lock = threading.Lock()
self_consistency_lock = threading.Lock()

summary_rows = []
self_consistency_results = {}  # Stores results of the 5 self-consistency runs

# Unified prompt type definition (originally named dir; renamed for clarity)
# dir = {0: 'RAW', 1: 'COT0', 2: 'COT', 3: 'COT1', 4: 'COT2', 5: 'COT3'}
dir = {0: 'COT0', 1: 'COT1', 2: 'COT2', 3: 'COT3'}#, 4: 'Few-Shots', 5: 'Few-Shots1'}
# Unified data type definition (includes bug_list_0.15)
data_type = {0: "mc", 1: "sc"}#, 2: "bug_list_0.15", 3: "mc_macro"}

def extract_result(text):
    """
    Logic for extracting the result:
    1. First look for "Check Status:" lines (handles cases with multiple critical variables)
    2. Match by priority:
       - If any line says "has not been checked" -> return "Has not been checked"
       - If all lines say "has been checked" -> return "Has been checked"
    3. If no Check Status line is found, search the whole text for negative/positive patterns
    """
    lower_text = text.lower()

    # Stage 1: find all "Check Status:" lines
    check_status_lines = []
    for line in text.split('\n'):
        if 'check status:' in line.lower():
            check_status_lines.append(line.lower())

    # If Check Status lines were found, process them by priority
    if check_status_lines:
        # Priority 1: check if any line has "has not been checked"
        for line in check_status_lines:
            if "has not been checked" in line:
                return "Has not been checked"

        # Priority 2: check if any line has "has been checked"
        for line in check_status_lines:
            if "has been checked" in line:
                return "Has been checked"

        # Priority 3: handle other phrasings of the result
        for line in check_status_lines:
            if "not" in line or "no" in line:
                return "Has not been checked"

        # Priority 4: default to "Has been checked" if a Check Status line was found but its content is ambiguous
        return "Has been checked"

    # Stage 2: if no Check Status line was found, search the whole text
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


def majority_voting(results):
    """
    Perform majority voting over results from multiple runs
    results: list containing the results of multiple runs
    Returns: the majority result and the vote tally
    """
    from collections import Counter
    result_counts = Counter(results)
    if not result_counts:
        return "Unknown", {}
    majority_result = result_counts.most_common(1)[0][0]
    return majority_result, dict(result_counts)


def recover_results_from_output_files(output_dir, model):
    """
    Recover already-analyzed results from the detailed output directory
    Used when the CSV file is missing but the detailed output files still exist

    Returns: [(prompt_type, sample_id, model, result, output_file), ...]
    """
    recovered_rows = []

    if not os.path.exists(output_dir):
        return recovered_rows

    try:
        # Scan all txt files in the output directory
        for filename in sorted(os.listdir(output_dir)):
            if filename.endswith("_output.txt") and filename.startswith(model):
                output_file = os.path.join(output_dir, filename)

                # Parse the sample ID
                try:
                    parts = filename.split("_")
                    sample_id = int(parts[-2])  # Assumes the format is {model}_{sample_id}_output.txt
                except (ValueError, IndexError):
                    continue

                # Read the file and extract the result
                try:
                    with open(output_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        result = extract_result(content)
                        recovered_rows.append([
                            "COT0_self-consistency",  # Marker indicating self-consistency
                            sample_id,
                            model,
                            result,
                            output_file
                        ])
                except Exception as e:
                    print(f"[Warning] Failed to read {output_file}: {e}")
                    continue
    except Exception as e:
        print(f"[Warning] Failed to recover results from {output_dir}: {e}")

    # Sort by sample ID
    recovered_rows.sort(key=lambda x: int(x[1]))
    return recovered_rows


def get_current_progress(data_type, dir_dict, dt, j, model, self_consistency=False):
    """
    Get the current analysis progress information
    Returns: (number of samples analyzed, total time, index of the next line to start from)
    """
    if self_consistency:
        output_csv = f"../data/ouput_results/{data_type[dt]}_COT0_self_{model}_result.csv"
    else:
        output_csv = f"../data/ouput_results/{data_type[dt]}_{dir_dict[j]}_{model}_result.csv"

    if not os.path.exists(output_csv):
        return 0, 0.0, 0

    analyzed_count = 0
    total_time = 0.0
    last_sample_id = 0

    try:
        with open(output_csv, "r", newline='', encoding="utf-8") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:  # Skip the header row
                    continue
                if row and len(row) > 0 and "Total analysis time" in str(row[0]):
                    time_str = str(row[0])
                    match = re.search(r'(\d+\.\d+)', time_str)
                    if match:
                        total_time = float(match.group(1))
                else:
                    analyzed_count += 1
                    if len(row) > 1:
                        try:
                            last_sample_id = int(row[1])
                        except:
                            pass
    except Exception as e:
        print(f"[Warning] Failed to read progress: {e}")
        return 0, 0.0, 0

    # Index of the next line = last_sample_id (sample IDs are 1-based, line indices are 0-based)
    next_line_index = last_sample_id
    return analyzed_count, total_time, next_line_index


def write_output(output_dir, output_file, model, content, i, j):
    os.makedirs(output_dir, exist_ok=True)
    with write_lock:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(f"Model: {model}\n")
            file.write(content)
        print(f"Written: {output_file}")
    # print("------------------------------------")
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

def analyze_prompt(client, model, prompt, i, j, is_online, dt, data_type, prompt_type):
    output_dir = f"../data/ouput_results/{data_type[dt]}/{prompt_type[j]}_{model}"
    output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
    analyze_output(output_dir, output_file, model, "", i, j)

def process_prompt(client, model, prompt, i, j, is_online, dt, data_type, prompt_type):
    # print(f"Processing prompt: 1{prompt}")
    if is_online:
        completion = client.chat.completions.create(
            model=model,
            web_search_options={},
            messages=[
                {"role": "system", "content": "You are a static analysis expert specialized in Linux kernel security."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2048
        )
    else:
        # print(f"Processing prompt: 2{prompt}")
        completion = client.chat.completions.create(
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
    # print(completion.choices[0].message.content)
    output_dir = f"../data/ouput_results/{data_type[dt]}/{prompt_type[j]}_{model}"
    output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
    write_output(output_dir, output_file, model, completion.choices[0].message.content, i, j)


def process_prompt_self_consistency(client, model, prompt, i, j, is_online, dt, data_type, prompt_type, num_runs=5):
    """
    Chain-of-Thought self-consistency: run multiple times and take a majority vote
    num_runs: number of runs (default 5)
    """
    results = []
    output_contents = []

    for run_idx in range(num_runs):
        if is_online:
            completion = client.chat.completions.create(
                model=model,
                web_search_options={},
                messages=[
                    {"role": "system", "content": "You are a static analysis expert specialized in Linux kernel security."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048
            )
        else:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a static analysis expert specialized in Linux kernel security."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,  # Use a nonzero temperature to obtain diversity
                max_completion_tokens=2048,
                top_p=0.95,  # Allow diversity
                frequency_penalty=0,
                presence_penalty=0,
            )

        content = completion.choices[0].message.content
        output_contents.append(content)
        result = extract_result(content)
        results.append(result)
        print(f"  Run {run_idx + 1}/{num_runs}: {result}")

    # Perform majority voting
    majority_result, vote_counts = majority_voting(results)

    # Save all run results and the voting result
    output_dir = f"../data/ouput_results/{data_type[dt]}/COT0_self_{model}"
    os.makedirs(output_dir, exist_ok=True)

    # Save the detailed results of all runs
    output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
    with write_lock:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(f"Model: {model}\n")
            file.write(f"Self-Consistency Results (5 runs):\n")
            file.write(f"{'='*60}\n")
            for run_idx, (content, result) in enumerate(zip(output_contents, results)):
                file.write(f"\n--- Run {run_idx + 1} ---\n")
                file.write(f"Result: {result}\n")
                file.write(f"Content:\n{content}\n")
            file.write(f"\n{'='*60}\n")
            file.write(f"Majority Voting Results:\n")
            file.write(f"Final Result: {majority_result}\n")
            file.write(f"Vote Distribution: {vote_counts}\n")
        print(f"Written: {output_file}")

    # Add the majority voting result to the summary
    with summary_lock:
        summary_rows.append([
            f"COT0_self-consistency",  # Prompt type with self-consistency marker
            i + 1,  # Sample ID
            model,
            majority_result,  # Use the majority voting result
            output_file
        ])

def build_prompts(file, number, code, code_context, type, function_label_info):
    return [
# ## old RAW prompt (updated 20251106)
#     f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers). A critical variable is any variable(e.g., pointers, error codes, status flags) used at the targeted line. A validation (or check) refers to any conditional test that ensures the variable’s correctness. A valid check must terminate execution on failure and allow normal execution on success.
#     Code Information:
#         File Path: {file}
#         Targeted Line Number: {number}
#         Targeted Line Code: {code}
#         Source Code Context: {code_context}
#     Output Format:
#         Critical Variable: <name or none>,
#         Check Status: <’The critical variable has been checked’ or ‘The critical variable has not been checked’>,
#         Evidence: <’The line(s) where the check occurs or explanation’>
#         Please strictly follow the above format. Do not use any other format.""",


## naive explicit COT prompt (with full code contexts)
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the targeted line:
A critical variable is any variable(e.g., pointers, error codes, status flags) used at the targeted line.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable. The check introduces two distinct branches: One branch must terminate or handle the error (e.g., return, goto error). The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Source Code Context: {code_context}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or ‘The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.""",


## 20251106 (+STC with full_code_contexts)
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the type of the targeted line:
- **Function call with return value:**  
  If the line involves a function call that returns a value — whether the return value is directly used in an expression or assigned to a variable — and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible),
then treat the return value or the assigned variable as the critical variable.
  - **Function call without return value:**  
  Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived from purely kernel-internal computations are generally *not* considered critical variables.
- **Array operation:**  
  The array index variable is the critical variable.
- **Other types:**  
  Select the most semantically significant variable that could affect safety or correctness as the critical variable.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable.
The check introduces two distinct branches:
One branch must terminate or handle the error (e.g., return, goto error).
The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Source Code Context: {code_context}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.""",

### +STC+PCCE prompt (20251106)
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the type of the targeted line:
- **Function call with return value:**  
  If the line involves a function call that returns a value — whether the return value is directly used in an expression or assigned to a variable — and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible),
then treat the return value or the assigned variable as the critical variable.
  - **Function call without return value:**  
  Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived from purely kernel-internal computations are generally *not* considered critical variables.
- **Array operation:**  
  The array index variable is the critical variable.
- **Other types:**  
  Select the most semantically significant variable that could affect safety or correctness as the critical variable.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable.
The check introduces two distinct branches:
One branch must terminate or handle the error (e.g., return, goto error).
The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Source Code Context: {code_context}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.""",

### add function labels prompt (20251111) (+STC+PCCE+FLG)
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the type of the targeted line and any available additional information:
- **Function call with return value:**  
  If the line involves a function call that returns a value — whether the return value is directly used in an expression or assigned to a variable — and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible),
then treat the return value or the assigned variable as the critical variable.
  - **Function call without return value:**  
  Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived from purely kernel-internal computations are generally *not* considered critical variables.
- **Array operation:**  
  The array index variable is the critical variable.
- **Other types:**  
  Select the most semantically significant variable that could affect safety or correctness as the critical variable.
If the additional information is not null, use it to identify the critical variable.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable.
The check introduces two distinct branches:
One branch must terminate or handle the error (e.g., return, goto error).
The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Source Code Context: {code_context}
Additional Information: {function_label_info}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.""",

## few-shots baseline
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the targeted line:
A critical variable is any variable(e.g., pointers, error codes, status flags) used at the targeted line.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable. The check introduces two distinct branches: One branch must terminate or handle the error (e.g., return, goto error). The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Source Code Context: {code_context}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.
Example 1:
{{
"File Path": "linux-4.20-rc5/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c",
"Targeted Line Number": 14040,
"Targeted Line Code": "rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);",
"Source Code Context": ['doorbell_size);//##14030', '}}//##14031', 'if (!bp->doorbells) {{//##14032', 'dev_err(&bp->pdev->dev,//##14033', '"Cannot map doorbell space, aborting\\n");//##14034', 'rc = -ENOMEM;//##14035', 'goto init_one_freemem;//##14036', '}}}}//##14037', '//##14038', 'if (IS_VF(bp)) {{{{//##14039', 'rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);//##14040', 'if (rc)//##14041', 'goto init_one_freemem;//##14042', '//##14043', '#ifdef CONFIG_BNX2X_SRIOV//##14044', '/* VF with OLD Hypervisor or old PF do not support filtering *///##14045', 'if (bp->acquire_resp.pfdev_info.pf_cap & PFVF_CAP_VLAN_FILTER) {{{{//##14046', 'dev->hw_features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14047', 'dev->features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14048', '}}}}//##14049', '#endif//##14050'],
"Output":
Critical Variable: rc,
Check Status: The critical variable has been checked,
Evidence: Lines 14041-14042: "if (rc) goto init_one_freemem;" which branches to error handling on nonzero rc, while normal execution continues otherwise.
}},
Example 2:
{{
"File Path": "linux-4.20-rc5/drivers/rtc/rtc-ds1374.c",
"Targeted Line Number": 449,
"Targeted Line Code": "ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);",
"Source Code Context": ['//##439', 'static void ds1374_wdt_disable(void)//##440', '{{{{//##441', 'int ret = -ENOIOCTLCMD;//##442', 'int cr;//##443', '//##444', 'cr = i2c_smbus_read_byte_data(save_client, DS1374_REG_CR);//##445', '/* Disable watchdog timer *///##446', 'cr &= ~DS1374_REG_CR_WACE;//##447', '//##448', 'ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);//##449', '}}}}//##450', '//##451', '/*//##452', '* Watchdog device is opened, and watchdog starts running.//##453', '*///##454', 'static int ds1374_wdt_open(struct inode *inode, struct file *file)//##455', '{{{{//##456', 'struct ds1374 *ds1374 = i2c_get_clientdata(save_client);//##457', '//##458', 'if (MINOR(inode->i_rdev) == WATCHDOG_MINOR) {{{{//##459'],
"Output":
Critical Variable: ret,
Check Status: The critical variable has not been checked,
Evidence: At line 449, ret is assigned from i2c_smbus_write_byte_data(...). The next line (450) closes the block, and there is no conditional check involving ret (e.g., if (ret < 0) …) in the provided context.
}},
Example 3:
{{
"File Path": "linux-4.20-rc5/drivers/media/dvb-frontends/stv090x.c",
"Targeted Line Number": 1456,
"Targeted Line Code": "STV090x_WRITE_DEMOD(state, CARCFG, 0x46);",
"Source Code Context": ['/* >= Cut 3 *///##1446', 'if (state->srate <= 5000000) {{{{//##1447', '/* enlarge the timing bandwidth for Low SR *///##1448', 'STV090x_WRITE_DEMOD(state, RTCS2, 0x68);//##1449', '}} else {{{{//##1450', '/* reduce timing bandwidth for high SR *///##1451', 'STV090x_WRITE_DEMOD(state, RTCS2, 0x44);//##1452', '}}}}//##1453', '//##1454', '/* Set CFR min and max to manual mode *///##1455', 'STV090x_WRITE_DEMOD(state, CARCFG, 0x46);//##1456', '//##1457', 'if (state->algo == STV090x_WARM_SEARCH) {{{{//##1458', '/* WARM Start//##1459', '* CFR min = -1MHz,//##1460', '* CFR max = +1MHz//##1461', '*///##1462', 'freq_abs  = 1000 << 16;//##1463', 'freq_abs /= (state->internal->mclk / 1000);//##1464', 'freq      = (s16) freq_abs;//##1465', '}} else {{{{//##1466'],
"Output":
Critical Variable: state,
Check Status: The critical variable has not been checked,
Evidence: The only condition in the provided context is "if (state->srate <= 5000000) {{ ... }} else {{ ... }}" (lines 1447–1453), which adjusts settings based on state->srate and does not validate the 'state' pointer nor introduce an error-handling branch. No explicit check (e.g., NULL check or error path) involving 'state' is present before the targeted line.
}},
Example 4:
{{
"File Path": "linux-4.20-rc5/drivers/md/dm-ioctl.c",
"Targeted Line Number": 1765,
"Targeted Line Code": "memcpy(dmi, param_kernel, minimum_data_size);",
"Source Code Context": ['//##1755', 'if (!dmi) {{//##1756', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1757', 'return -EFAULT;//##1758', 'return -ENOMEM;//##1759', '}}//##1760', '//##1761', '*param_flags |= DM_PARAMS_MALLOC;//##1762', '//##1763', '/* Copy from param_kernel (which was already copied from user) *///##1764', 'memcpy(dmi, param_kernel, minimum_data_size);//##1765', '//##1766', 'if (copy_from_user(&dmi->data, (char __user *)user + minimum_data_size,//##1767', 'param_kernel->data_size - minimum_data_size))//##1768', 'goto bad;//##1769', 'data_copied://##1770', '/* Wipe the user buffer so we do not return it to userspace *///##1771', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1772', 'goto bad;//##1773', '//##1774', '*param = dmi;//##1775'],
"Output":
Critical Variable: dmi,
Check Status: The critical variable has been checked,
Evidence: The check occurs at line 1755 where `if (!dmi)` evaluates the critical variable dmi, and if it is NULL, the function returns -ENOMEM at line 1758, which represents error handling. This satisfies the requirement of a valid check with two distinct branches: one for error handling (return -ENOMEM) and another for normal execution (continuing past the if block).
}}""",

## few-shots + LLMSA-MC
f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions:
Step 1: Determine the *critical variable* depending on the type of the targeted line and any available additional information:
- **Function call with return value:**
  If the line involves a function call that returns a value — whether the return value is directly used in an expression or assigned to a variable — and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible),
then treat the return value or the assigned variable as the critical variable.
  - **Function call without return value:**
  Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived from purely kernel-internal computations are generally *not* considered critical variables.
- **Array operation:**
  The array index variable is the critical variable.
- **Other types:**
  Select the most semantically significant variable that could affect safety or correctness as the critical variable.
If the additional information is not null, use it to identify the critical variable.
Step 2: Examine whether the critical variable is validated in the code context:
A valid check must satisfy all of the following:
The condition explicitly involves the critical variable.
The check introduces two distinct branches:
One branch must terminate or handle the error (e.g., return, goto error).
The other branch continues normal execution.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Source Code Context: {code_context}
Additional Information: {function_label_info}
Output Format:
Critical Variable: <name or none>,
Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
Evidence: <'The line(s) where the check occurs or explanation'>,
Please strictly follow the above format. Do not use any other format.
Example 1:
{{
"File Path": "linux-4.20-rc5/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c",
"Targeted Line Number": 14040,
"Targeted Line Code": "rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);",
"Targeted Line Type": "Returning Function Call",
"Source Code Context": ['rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);//##14040','if (rc)//##14041','goto init_one_freemem;//##14042','//##14043','#ifdef CONFIG_BNX2X_SRIOV//##14044','/* VF with OLD Hypervisor or old PF do not support filtering *///##14045','if (bp->acquire_resp.pfdev_info.pf_cap & PFVF_CAP_VLAN_FILTER) {{{{//##14046','dev->hw_features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14047','dev->features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14048','}}}}//##14049'],
"Output":
Critical Variable: rc,
Check Status: The critical variable has been checked,
Evidence: Lines 14041-14042: "if (rc) goto init_one_freemem;" which branches to error handling on nonzero rc, while normal execution continues otherwise.
}},
Example 2:
{{
"File Path": "linux-4.20-rc5/drivers/rtc/rtc-ds1374.c",
"Targeted Line Number": 449,
"Targeted Line Code": "ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);",
"Targeted Line Type": "Returning Function Call",
"Source Code Context": ['ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);//##449','}}}}//##450','//##451','/*//##452','* Watchdog device is opened, and watchdog starts running.//##453','*///##454','static int ds1374_wdt_open(struct inode *inode, struct file *file)//##455','{{{{//##456','struct ds1374 *ds1374 = i2c_get_clientdata(save_client);//##457','//##458'],
"Output":
Critical Variable: ret,
Check Status: The critical variable has not been checked,
Evidence: At line 449, ret is assigned from i2c_smbus_write_byte_data(...). The next line (450) closes the block, and there is no conditional check involving ret (e.g., if (ret < 0) …) in the provided context.
}},
Example 3:
{{
"File Path": "linux-4.20-rc5/drivers/media/dvb-frontends/stv090x.c",
"Targeted Line Number": 1456,
"Targeted Line Code": "STV090x_WRITE_DEMOD(state, CARCFG, 0x46);",
"Targeted Line Type": "Void Function Call",
"Source Code Context": "['/* >= Cut 3 *///##1446','if (state->srate <= 5000000) //##1447','/* enlarge the timing bandwidth for Low SR *///##1448','STV090x_WRITE_DEMOD(state, RTCS2, 0x68);//##1449','else {{{{//##1450','/* reduce timing bandwidth for high SR *///##1451','STV090x_WRITE_DEMOD(state, RTCS2, 0x44);//##1452','}}}}//##1453','//##1454','/* Set CFR min and max to manual mode *///##1455']",
"Output":
Critical Variable: state,
Check Status: The critical variable has not been checked,
Evidence: The only condition in the provided context is "if (state->srate <= 5000000) {{ ... }} else {{ ... }}" (lines 1447–1453), which adjusts settings based on state->srate and does not validate the 'state' pointer nor introduce an error-handling branch. No explicit check (e.g., NULL check or error path) involving 'state' is present before the targeted line.
}},
Example 4:
{{
"File Path": "linux-4.20-rc5/drivers/md/dm-ioctl.c",
"Targeted Line Number": 1765,
"Targeted Line Code": "memcpy(dmi, param_kernel, minimum_data_size);",
"Targeted Line Type": "Void Function Call",
"Source Code Context": "['//##1755', 'if (!dmi) {{//##1756', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1757', 'return -EFAULT;//##1758', 'return -ENOMEM;//##1759', '}}//##1760', '//##1761', '*param_flags |= DM_PARAMS_MALLOC;//##1762', '//##1763', '/* Copy from param_kernel (which was already copied from user) *///##1764']",
"Output":
Critical Variable: dmi,
Check Status: The critical variable has been checked,
Evidence: The check occurs at line 1755 where `if (!dmi)` evaluates the critical variable dmi, and if it is NULL, the function returns -ENOMEM at line 1758, which represents error handling. This satisfies the requirement of a valid check with two distinct branches: one for error handling (return -ENOMEM) and another for normal execution (continuing past the if block).
}}"""
]


def parse_line(line):
    """
    Parse a line of data, supporting different data type file formats

    Standard format (mc_classify/sc_classify/bug_list_0.15_classify.list/mc_macro_classify.list):
        file_path ;; line_no ;; line_code ;; context_code ;; type

    Supports two formats:
    - With sequence number: seq_num ;; file_path ;; line_no ;; ...
    - Without sequence number: file_path ;; line_no ;; ...
    """
    parts = line.strip().split(" ;; ")

    # Standard format: the sequence number comes first but is typically skipped
    # Actual format: file_path ;; line_no ;; line_code ;; context ;; type ;; ...
    start_idx = 0

    # Check whether the first field is a sequence number (digit)
    # if parts[0].strip().isdigit() and len(parts) >= 6:
    #     start_idx = 1  # Skip the sequence number

    # Extract the basic fields
    abs_path = parts[start_idx].strip()
    rel_path = abs_path.replace("../data/kernel-code/", "")
    file_path = rel_path

    line_no = parts[start_idx + 1].strip() if len(parts) > start_idx + 1 else ""
    line_code = parts[start_idx + 2].strip() if len(parts) > start_idx + 2 else ""
    context_code = parts[start_idx + 3].strip() if len(parts) > start_idx + 3 else ""

    # Extract the optional fields
    raw_type = parts[start_idx + 4].strip() if len(parts) > start_idx + 4 else ""
    # extra_info = parts[start_idx + 5].strip() if len(parts) > start_idx + 5 else ""

    return file_path, line_no, line_code, context_code, raw_type


def llm_analysis(client, model_list, is_online_model, data_type, prompt_type, dt=0, j=0, missing_ids=None, self_consistency=False, start_line=None):

    """
    Main function for analyzing prompts
    Parameters:
    - dt: data type index (0:mc, 1:sc, 2:bug_list_0.15, 3:mc_macro)
    - j: prompt type index (0:COT0, 1:COT1, 2:COT2, 3:COT3, 4:Few-Shots, 5:Few-Shots+LLMSA-MC)
    - missing_ids: list of sample IDs to analyze (1-based, e.g. [1, 2, 3, 5]). If None, analyze all samples
    - self_consistency: whether to enable Chain-of-Thought self-consistency (run each sample 5 times)
    - start_line: which line to start analysis from (0-based, used to resume an interrupted analysis)
    """

    # Determine the configuration strategy based on the prompt_type index
    # COT0: naive prompt: type="", function_label_info="", file: classify_full_contexts.list
    # COT1: +STC prompt: type is set, function_label_info="", file: classify_full_contexts.list
    # COT2: +STC+PCCE prompt: type is set, function_label_info="", file: classify.list
    # COT3: +STC+PCCE+FLG prompt: type is set, function_label_info is set, file: classify.list
    # Few-Shots: basic few-shot learning example, uses the COT0 strategy
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

    print(f"[Config] use_type={use_type}, use_function_labels={use_function_labels}, file={list_file}")

    # If function_labels are needed, read them from the corresponding file
    function_labels = {}
    if use_function_labels:
        labels_file = f"../data/{data_type[dt]}_classify_function_labels.list"
        print(f"[Loading] Reading function labels from {labels_file}")
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
            print(f"[Loaded] Total {len(function_labels)} function labels loaded")
        except FileNotFoundError:
            print(f"[Warning] Function labels file not found: {labels_file}")

    start_time = time.time()

    # If missing_ids is specified, only analyze those samples (convert 1-based to 0-based)
    sample_indices = None
    if missing_ids:
        sample_indices = set(id - 1 for id in missing_ids)  # Convert to 0-based indices
        print(f"[Config] Analyzing only missing samples: {sorted(missing_ids)}")

    # Set the concurrency level: use max_workers=1 (sequential) when analyzing missing_ids, otherwise max_workers=8
    # Sequential execution is also used in self-consistency mode (5 runs per sample)
    max_workers = 1 if missing_ids else 8
    max_workers = 1 if data_type[dt] == "mc_macro" else max_workers  # The mc_macro dataset also uses sequential execution
    max_workers = 1 if self_consistency else max_workers  # Sequential execution is used in self-consistency mode

    try:
        with open(list_file, "r", encoding='utf-8') as f:
            lines = f.readlines()

            # Determine the start line (convert the 1-based sample number to a 0-based index)
            # start_line is 1-based (e.g., 146 means the 146th sample), needs to be converted to a 0-based index (145)
            start_idx = (start_line - 1) if start_line is not None else 0
            if start_line is not None:
                print(f"[Config] Resuming from sample {start_line} (1-based, starting at index {start_idx})")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for i in range(start_idx, len(lines)):
                    # If sample IDs were specified, only process those samples
                    if sample_indices is not None and i not in sample_indices:
                        continue

                    # Use the unified parsing function
                    file_path, line_no, line_code, context_code, raw_type = parse_line(lines[i])

                    # Decide whether to use type based on the strategy
                    if use_type:
                        if raw_type == 'Returning Function Call':
                            line_type = 'Function call with return value'
                        elif raw_type == 'Void Function Call':
                            line_type = 'Function call without return value'
                        elif raw_type == 'Array Access':
                            line_type = 'Array Operation'
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
                    # Self-consistency mode always uses COT0 (j=0)
                    prompt_idx = 0 if self_consistency else j
                    prompt = build_prompts(file_path, line_no, line_code, context_code, line_type, function_label_info)[prompt_idx]

                    for model in model_list:
                        if self_consistency:
                            executor.submit(
                                process_prompt_self_consistency,
                                client,
                                model,
                                prompt,
                                i,
                                0,  # Always use COT0
                                is_online_model,
                                dt,
                                data_type,
                                prompt_type,
                                num_runs=5
                            )
                        else:
                            executor.submit(
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
                # The ThreadPoolExecutor context manager automatically waits for all tasks to finish

    except FileNotFoundError as e:
        print(f"[Error] File not found: {e}")
        return
    except Exception as e:
        print(f"[Error] Unexpected error: {e}")
        raise

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n[Complete] Total analysis time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")

    # Return the analysis time and sample statistics
    # samples_processed: number of samples processed in this run
    # total_samples: total number of samples in the data file
    total_lines = len(lines) if 'lines' in locals() else 0
    samples_processed = total_lines - (start_line if start_line else 0)
    return elapsed_time, samples_processed, total_lines

def is_responses_api_model(model):
    """Check whether the model uses the responses.create() API"""
    responses_models = ['DeepSeek-R1', 'Qwen3-Coder']
    return any(model_name in model for model_name in responses_models)
                    
def test_api_connection(client, model):
    """Test whether the API connection is working"""
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
    parser.add_argument('--self-consistency', action='store_true', default=False,
                        help='Enable Chain-of-Thought self-consistency (run each sample 5 times with majority voting)')
    parser.add_argument('--start-line', type=int, default=None,
                        help='Start analysis from specific sample number (1-based, e.g., 146 means start from sample 146, like --missing-ids)')
    parser.add_argument('--previous-time', type=float, default=None,
                        help='Previous analysis time (in seconds) before --start-line, for calculating total time when CSV was not saved')
    parser.add_argument('--check-progress', action='store_true', default=False,
                        help='Check current analysis progress and show next line to resume from')
    return parser.parse_args()


if __name__ == '__main__':
    args = create_parser()

    client = OpenAI(
        ## aihubmix.com API key
        base_url="https://aihubmix.com/v1",
        api_key="sk-zZa4lJoKCuiLtklk7913Ab1e6a74438e84C84c5b993e09F6",
        ## zhizengzeng.com API key
        # base_url="https://api.zhizengzeng.com/v1",
        # api_key="sk-zk2bc58a1cc3a1160bbbea90c5256adc56f6a3c9229af1e2",
        http_client=httpx.Client(
        proxy="http://127.0.0.1:7897",
        ),
    )

    # Mapping of model online status (whether web_search_options is needed)
    model_online_status = {
        'DeepSeek-V3': False,
        'qwen3-coder-480b-a35b-instruct': False,
        'llama-3.3-70b': False,
        # 'qwen3-coder-plus-2025-07-22': False,
        'gpt-4o': False,
        # 'DeepSeek-R1': False,
        'claude-sonnet-4-20250514': False,
        # 'Qwen3-Coder': False,
        'gemini-2.5-pro': False,
    }

    # Use the globally defined data_type and prompt_type
    # data_type = {0: "mc", 1: "sc", 2: "bug_list_0.15", 3: "mc_macro"}
    # prompt_type = {0: 'RAW', 1: 'COT0', 2: 'COT', 3: 'COT1', 4: 'COT2', 5: 'COT3'}


    # Handle command-line arguments - supports single debug mode or batch processing
    # if args.single_model:
    #     model_list = [args.single_model]
    # else:
    #     model_list = args.models
    # else:
    #     model_list = ['qwen3-coder-plus-2025-07-22']
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

    # Only COT0 is used in self-consistency mode
    if args.self_consistency:
        prompt_type_indices = [0]  # Only use COT0 (index 0)

    print(f"Models: {model_list}")
    print(f"Data types: {[data_type[i] for i in data_type_indices]}")
    print(f"Prompt types: {[dir[i] for i in prompt_type_indices]}")
    if args.self_consistency:
        print(f"Mode: Chain-of-Thought Self-Consistency (5 runs per sample with majority voting)")
    if args.missing_ids:
        print(f"Missing sample IDs to analyze: {args.missing_ids}")
    print()

    # If --check-progress is specified, show the current progress and exit
    if args.check_progress:
        print("\n" + "="*70)
        print("ANALYSIS PROGRESS CHECK")
        print("="*70)
        for dt in data_type_indices:
            for j in prompt_type_indices:
                for model in model_list:
                    analyzed, total_time, next_line = get_current_progress(data_type, dir, dt, j, model, args.self_consistency)
                    print(f"\nModel: {model}")
                    print(f"Data Type: {data_type[dt]}")
                    print(f"Prompt Type: {dir[j]}")
                    print(f"  Analyzed samples: {analyzed}")
                    print(f"  Total time spent: {total_time:.2f}s ({total_time/60:.2f} minutes)")
                    if analyzed > 0:
                        print(f"  Next line to resume: {next_line}")
                        print(f"  Resume command: --start-line {next_line}")
                    print(f"  CSV File: ../data/ouput_results/{data_type[dt]}_COT0_self_{model}_result.csv" if args.self_consistency else f"  CSV File: ../data/ouput_results/{data_type[dt]}_{dir[j]}_{model}_result.csv")
        print("\n" + "="*70)
        print("To resume analysis, use: --start-line <next_line_number>")
        print("="*70)
        sys.exit(0)
        
        # Test the API connection before starting the analysis
    api_ok = False
    for model in model_list:
        if test_api_connection(client, model):
            api_ok = True
            break

    if not api_ok:
        print("[CRITICAL] API connection failed!")
        exit(1)

    # Iterate over all combinations to perform the analysis
    for dt in data_type_indices:
        for j in prompt_type_indices:
            for model in model_list:
                # Determine whether the model is online
                is_online_model = model_online_status.get(model, False)

                print(f"\n{'='*60}")
                print(f"Processing: Model={model}, DataType={data_type[dt]}, PromptType={dir[j]}")
                print(f"{'='*60}")

                summary_rows.clear()

                # Call llm_analysis to perform the analysis, passing dt and j as parameters, along with the missing sample IDs
                # Check whether self-consistency mode is enabled
                self_consistency_mode = args.self_consistency if hasattr(args, 'self_consistency') else False
                start_line = args.start_line if hasattr(args, 'start_line') else None
                previous_time = args.previous_time if hasattr(args, 'previous_time') else None
                result = llm_analysis(client, [model], is_online_model, data_type, dir, dt=dt, j=j, missing_ids=args.missing_ids, self_consistency=self_consistency_mode, start_line=start_line)

                # Handle the return value (may be a tuple or a single value, depending on the script version)
                if isinstance(result, tuple):
                    elapsed_time, samples_processed, total_samples = result
                else:
                    elapsed_time = result
                    samples_processed = 0
                    total_samples = 0

                # Generate a CSV result for each combination
                if self_consistency_mode:
                    output_csv = f"../data/ouput_results/{data_type[dt]}_COT0_self_{model}_result.csv"
                else:
                    output_csv = f"../data/ouput_results/{data_type[dt]}_{dir[j]}_{model}_result.csv"
                os.makedirs(os.path.dirname(output_csv), exist_ok=True)

                # Initialize the previous analysis time
                previous_time = 0
                time_source = "none"  # Track the source of the time value: csv, specified, inferred, none

                # If resuming analysis from a specific line (--start-line), handle the previous analysis time
                if args.start_line:
                    # Priority 1: extract the saved time from the CSV file
                    csv_time_found = False
                    if os.path.exists(output_csv):
                        try:
                            with open(output_csv, "r", newline='', encoding="utf-8") as f:
                                reader = csv.reader(f)
                                for i, row in enumerate(reader):
                                    if row and len(row) > 0 and "Total analysis time" in str(row[0]):
                                        time_str = str(row[0])
                                        match = re.search(r'(\d+\.\d+)', time_str)
                                        if match:
                                            previous_time = float(match.group(1))
                                            csv_time_found = True
                                            time_source = "csv"
                                            print(f"[Info] Read previous analysis time from CSV: {previous_time:.2f} seconds ({previous_time/60:.2f} minutes)")
                                            break
                        except Exception as e:
                            print(f"[Warning] Failed to read previous time from CSV: {e}")

                    # Priority 2: if the CSV has no time recorded, use the --previous-time argument
                    if not csv_time_found and args.previous_time is not None:
                        previous_time = args.previous_time
                        time_source = "specified"
                        print(f"[Info] Using specified previous time: {previous_time:.2f} seconds ({previous_time/60:.2f} minutes)")

                    # Priority 3: if neither is available, infer the total time from this run's elapsed time
                    if not csv_time_found and args.previous_time is None:
                        print(f"[Info] No previous analysis time found in CSV and --previous-time not specified")
                        if samples_processed > 0 and total_samples > 0:
                            # Compute the average time per sample
                            avg_time_per_sample = elapsed_time / samples_processed
                            # Inferred total time = total number of samples * average time per sample
                            inferred_total_time = total_samples * avg_time_per_sample
                            # Previously elapsed time = inferred total time - time elapsed this run
                            inferred_previous_time = inferred_total_time - elapsed_time
                            previous_time = inferred_previous_time
                            time_source = "inferred"
                            print(f"[Info] Inferring previous time based on current session performance...")
                            print(f"[Info]   Samples processed this session: {samples_processed}")
                            print(f"[Info]   Total samples in dataset: {total_samples}")
                            print(f"[Info]   Average time per sample: {avg_time_per_sample:.4f}s")
                            print(f"[Info]   Inferred previous time: {inferred_previous_time:.2f}s ({inferred_previous_time/60:.2f} minutes)")
                            print(f"[Info]   Inferred total time for full dataset: {inferred_total_time:.2f}s ({inferred_total_time/60:.2f} minutes)")
                        else:
                            print(f"[Info] Cannot infer previous time (insufficient data)")
                            print(f"[Info] To include previous time, use: --previous-time <seconds>")

                # If this run supplemented data via missing_ids or start_line, append it to the original file
                if args.missing_ids or args.start_line:
                    # Read the contents of the original file (excluding the final time-summary row)
                    existing_rows = []
                    total_time = elapsed_time + previous_time

                    if os.path.exists(output_csv):
                        with open(output_csv, "r", newline='', encoding="utf-8") as f:
                            reader = csv.reader(f)
                            for i, row in enumerate(reader):
                                if i == 0:  # Skip the header row
                                    continue
                                # Skip the final time-summary row (usually contains "Total analysis time")
                                if row and len(row) > 0 and "Total analysis time" in str(row[0]):
                                    continue  # Skip it directly; the time is no longer handled separately here
                                else:
                                    existing_rows.append(row)
                        if args.missing_ids:
                            print(f"[Info] Appending {len(summary_rows)} new samples to existing file (missing IDs mode)")
                        else:
                            print(f"[Info] Appending {len(summary_rows)} new samples to existing file (resume from sample {args.start_line})")
                    elif args.start_line and self_consistency_mode:
                        # If the CSV doesn't exist but --start-line was used, try to recover from the detailed output directory
                        print(f"[Info] CSV file not found, attempting to recover results from output directory...")
                        output_detail_dir = f"../data/ouput_results/{data_type[dt]}/COT0_self_{model}"
                        recovered_rows = recover_results_from_output_files(output_detail_dir, model)
                        if recovered_rows:
                            existing_rows = recovered_rows
                            print(f"[Info] ✅ Recovered {len(existing_rows)} results from output directory")
                            # Update the time: if no CSV time was read, use the inferred or specified value
                            if time_source == "none" and samples_processed > 0 and total_samples > 0:
                                # If there's still no time, use the inferred or specified value
                                if previous_time == 0:
                                    print(f"[Info] No previous time found, will use --previous-time or inferred time")
                        else:
                            print(f"[Info] No previous results found in output directory")

                    # Write the original rows + new rows (containing all results from the first to the last line)
                    total_data_rows = len(existing_rows) + len(summary_rows)
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(existing_rows)
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV updated to {output_csv}")
                    print(f"  📋 Total results in CSV: {total_data_rows} rows")
                    if existing_rows:
                        print(f"     - Previously analyzed: {len(existing_rows)} rows")
                        print(f"     - New analysis: {len(summary_rows)} rows")
                    if args.start_line:
                        if previous_time > 0:
                            print(f"  📊 Time breakdown:")
                            print(f"     Current session (from sample {args.start_line}): {elapsed_time:.2f}s ({elapsed_time/60:.2f} minutes)")
                            print(f"     Previous analysis time: {previous_time:.2f}s ({previous_time/60:.2f} minutes)")
                            print(f"     📈 Total: {total_time:.2f}s ({total_time/60:.2f} minutes)")

                            # Add extra information based on the time source
                            if time_source == "csv":
                                print(f"     [Source: CSV file]")
                            elif time_source == "specified":
                                print(f"     [Source: --previous-time parameter]")
                            elif time_source == "inferred":
                                print(f"     [Source: Inferred from current session performance]")
                                print(f"     ⚠️  Note: This is an estimate based on {samples_processed} samples. Accuracy depends on consistent performance.")
                        else:
                            print(f"  ⏱️  Current session time (from sample {args.start_line}): {elapsed_time:.2f}s ({elapsed_time/60:.2f} minutes)")
                            print(f"     (No previous time recorded. Use --previous-time to add it)")
                else:
                    # Normal case: create a new file
                    total_time = elapsed_time
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV written to {output_csv}")