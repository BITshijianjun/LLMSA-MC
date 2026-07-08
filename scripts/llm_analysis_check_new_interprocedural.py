import os
import threading
import csv
import argparse
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import time
import re
import logging

write_lock = threading.Lock()
summary_lock = threading.Lock()
log_lock = threading.Lock()

summary_rows = []
prompt_logs = []
enable_prompt_log = False  # 全局开关：是否启用 prompt 日志记录

# 统一的提示类型定义
dir = {0: 'COT4', 1: 'COT5', 2: 'COT6', 3: 'COT7'}
# 统一的数据类型定义（包括 mc_cross 的新格式）
data_type = {0: "mc_cross", 1: "sc_cross"}

def extract_result(text):
    """
    提取结果的逻辑：
    1. 优先查找 "Check Status:" 行（处理可能的多个关键变量）
    2. 按优先级匹配：
       - 如果有任何 "has not been checked" → 返回 "Has not been checked"
       - 如果都是 "has been checked" → 返回 "Has been checked"
    3. 如果没有找到 Check Status，则全文搜索负面/正面模式
    """
    lower_text = text.lower()

    # 第一阶段：查找所有 "Check Status:" 行
    check_status_lines = []
    for line in text.split('\n'):
        if 'check status:' in line.lower():
            check_status_lines.append(line.lower())

    # 如果找到了 Check Status 行，按优先级处理
    if check_status_lines:
        # 优先级1：检查是否有任何 "has not been checked"
        for line in check_status_lines:
            if "has not been checked" in line:
                return "Has not been checked"

        # 优先级2：检查是否有 "has been checked"
        for line in check_status_lines:
            if "has been checked" in line:
                return "Has been checked"

        # 优先级3：如果有其他形式的结果表述
        for line in check_status_lines:
            if "not" in line or "no" in line:
                return "Has not been checked"

        # 优先级4：默认返回 "Has been checked" 如果找到了 Check Status 但无法确定内容
        return "Has been checked"

    # 第二阶段：如果没有找到 Check Status，则进行全文搜索
    # 优先级：先搜索负面模式（更严格）
    negative_patterns = [
        "has not been checked",
        "not properly validated",
        "not checked",
        "not validated",
    ]
    for pat in negative_patterns:
        if pat in lower_text:
            return "Has not been checked"

    # 再搜索正面模式
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
    """记录发送给 LLM 的 prompt 到日志文件（如果启用）"""
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
    output_dir = f"../data/test_data/test_results_2026/{data_type[dt]}/{prompt_type[j]}_{model}"
    output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
    analyze_output(output_dir, output_file, model, "", i, j)

def process_prompt(client, model, prompt, i, j, is_online, dt, data_type, prompt_type):
    try:
        # 记录 prompt 到日志
        log_prompt(model, i + 1, prompt_type[j], prompt, data_type[dt])

        output_dir = f"../data/test_data/test_results_2026/{data_type[dt]}/{prompt_type[j]}_{model}"
        output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")

        selected_client = client

        # DeepSeek-R1 使用 responses.create()，其他模型使用 chat.completions.create()
        # if model == 'deepseek-r1':
        #     # 使用 responses.create() API
        #     print(f"[Stream] Calling responses.create() for {model}")
        #     response = selected_client.responses.create(
        #         model=model,
        #         input=prompt,
        #         reasoning={"effort": "minimal"},
        #         text={"verbosity": "low"},
        #         stream=True
        #     )

        #     # 处理流式响应
        #     print(f"[Stream] Iterating over response stream...")
        #     collected_text = ""
        #     event_count = 0

        #     try:
        #         for event in response:
        #             event_count += 1
        #             event_str = str(event)

        #             # 收集事件文本
        #             if event_str and not event_str.startswith('<'):
        #                 print(f"[Stream] Event {event_count}: {event_str[:80]}")
        #                 collected_text += event_str + "\n"
        #             else:
        #                 print(f"[Stream] Event {event_count}: {type(event).__name__}")

        #         print(f"[Stream] Processed {event_count} events, collected {len(collected_text)} chars")

        #         if collected_text.strip():
        #             write_output(output_dir, output_file, model, collected_text, i, j)
        #         else:
        #             error_msg = f"[Stream Error] No content collected from {event_count} events"
        #             write_output(output_dir, output_file, model, error_msg, i, j)

        #     except Exception as stream_error:
        #         print(f"[ERROR] Stream processing failed: {str(stream_error)}")
        #         error_msg = f"Stream processing error: {str(stream_error)}"
        #         write_output(output_dir, output_file, model, error_msg, i, j)

        # 使用 chat.completions.create() API（其他模型）
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
        output_dir = f"../data/test_data/test_results_2026/{data_type[dt]}/{prompt_type[j]}_{model}"
        output_file = os.path.join(output_dir, f"{model}_{i + 1}_output.txt")
        error_msg = f"Error: {str(e)}\nFailed to call model API. Please check:\n1. API key validity\n2. Network connection\n3. Model name correctness\n4. API endpoint accessibility"
        write_output(output_dir, output_file, model, error_msg, i, j)

def build_prompts(file, number, code, caller_function, callsite, code_context, type, function_label_info, parameter_annotation):
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


## naive explicit COT prompt (with full code contexts) ---- for interprocedural analysis --- 20260627
# f"""Analyze the Linux kernel code and determine whether the critical variable associated with the targeted line is properly validated using the provided source code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions:
# Step 1: Determine the critical variable.
# A critical variable is the variable whose correctness or validity is required for the safe execution of the targeted line (e.g., pointers, error codes, status flags).
# If caller information is provided, use all available information together with the provided source code context to identify the critical variable.
# Step 2: Determine whether the critical variable is properly validated.
# A valid validation must satisfy all of the following:
# - The condition explicitly involves the critical variable.
# - The condition introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# The validation may appear anywhere within the provided source code context.
# A potentially unsafe use refers to an operation whose safe execution depends on the validity of the critical variable (e.g., pointer dereference, array indexing, function invocation using the variable, or the use of an error code without prior validation).
# Determine whether the validation occurs before the first potentially unsafe use of the critical variable within the provided source code context.
# Step 3: Provide the analysis result according to the specified output format.
# Important:
# Your analysis must be based only on the provided source code context and the supplied caller information. Do not make speculative inferences beyond the provided code.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line.
# Callsite: {callsite}
# The function call statement that invokes the function containing the targeted line.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.""",

# ## naive explicit COT prompt (with full code contexts) ---- for interprocedural analysis --- 20260627
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions:
# Step 1: Determine the critical variable depending on the targeted line.
# A critical variable is the variable (e.g., a pointer, error code, or status flag) whose correctness or validity is required for the safe execution of the targeted line.
# If caller information is provided, use the caller function and the corresponding callsite to understand the relationship between the targeted line and its calling context when identifying the critical variable and determining whether it has been validated.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy all of the following:
# - The condition explicitly involves the critical variable or its corresponding variable appearing at the provided callsite.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# The validation may appear anywhere in the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
# Step 3: Provide the analysis result according to the specified output format.
# Important:
# Your analysis must be based only on the provided source code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.""",

## naive explicit COT prompt (with full code contexts) ---- for interprocedural analysis --- 20260705
# f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Analysis Instructions:
# Step 1: Determine the analysis mode and identify the critical variable.
# A critical variable is the variable whose correctness or validity is required for the safe execution of the targeted line (e.g., pointers, error codes, status flags).
# Use all available information together with the provided source code context to identify the critical variable. 
# If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line and the corresponding callsite argument.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The control-flow predicate must directly evaluate the critical variable identified in Step 1. 
# - The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check. Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code. If no code pattern satisfying all of the above requirements exists in the provided context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format:
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.""",

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


## naive explicit COT prompt (with full code contexts) ---- for interprocedural analysis --- 20260630
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please explicitly perform and report the following analysis procedure before producing the final result. The analyses of Steps 1 and 2 are required parts of the response and must not be omitted, even if the final answer appears straightforward.
# Analysis Requirements
# Perform the analysis sequentially according to the steps below.
# Each step depends on the result of the previous step and must not be skipped, merged, or reordered.
# Specifically:
# - Step 1 must identify the critical variable and explain why it is selected.
# - Step 2 must evaluate only the critical variable identified in Step 1 and report the supporting evidence.
# - Step 3 must summarize the conclusions from Steps 1 and 2 without introducing new analysis.
# Once the critical variable has been identified in Step 1, do not redefine, replace, or refine it during later steps.
# Step-by-Step Reasoning Instructions:
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# A critical variable is the variable whose correctness or validity is required for the safe execution of the targeted line (e.g., pointers, error codes, status flags).
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# Use all available information together with the provided source code context to identify the critical variable.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context.
# A valid check must satisfy all of the following:
# * The condition explicitly involves the critical variable identified in Step 1, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation must be supported by explicit evidence in the provided source code context.
# Do not conclude that the critical variable has been checked solely based on function semantics, prior usage, subsystem-specific programming patterns, programmer intent, coding conventions, or assumptions about omitted code.
# Reasonable interpretations of explicit control-flow conditions are allowed, but every reported validation must be directly supported by the provided source code context.
# If no explicit evidence satisfying the above criteria exists in the provided code context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Do not introduce new evidence, identify a new critical variable, or revise the conclusions from previous steps.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",


## 20260629 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the critical variable depending on the targeted line.
# A critical variable is the variable (e.g., a pointer, error code, or status flag) whose correctness or validity is required for the safe execution of the targeted line.
# Determine the critical variable according to the targeted line type:
# • Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible), treat the return value or the assigned variable as the critical variable.
# • Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# • Array operation:
# Treat the array index variable as the critical variable.
# • Other types:
# Select the most semantically significant variable whose correctness is required for the safe execution of the targeted line.
# If caller information is provided, perform an inter-procedural analysis by jointly considering the targeted line and the corresponding callsite.
# If Parameter Annotation is "Yes", the identified critical variable is a formal parameter of the enclosing function. Identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding argument as representing the same critical variable across the function boundary.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation may appear anywhere within the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
# Only consider validations that occur **before the first potentially unsafe use** of the critical variable.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ## 20260630 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the object whose validity is required for the safe execution of the targeted line.
# If the targeted line directly accesses a formal parameter or one of its members (e.g., `dev`, `dev->name`), treat the formal parameter (e.g., `dev`) as the critical variable.
# If the targeted line contains chained pointer-member accesses (e.g., `dev->name->addr`), identify the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# Then identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation may appear anywhere within the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
# Only consider validations that occur **before the first potentially unsafe use** of the critical variable.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ## 20260630-1 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Reasoning Requirements
# Perform the analysis sequentially according to the steps below.
# Each step depends on the result of the previous step and must not be skipped, merged, or reordered.
# Specifically:
# - Step 1 identifies the critical variable.
# - Step 2 evaluates only the critical variable identified in Step 1.
# - Step 3 produces the final result based solely on the conclusions from Steps 1 and 2.
# Once the critical variable has been identified in Step 1, do not redefine, replace, or refine it during later steps.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the critical variable solely based on the targeted line. The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# After identifying the critical variable, determine whether it originates from a formal parameter. If so, identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation must be supported by explicit evidence in the provided source code context.
# Do not conclude that the critical variable has been checked solely based on function semantics, prior usage, subsystem-specific programming patterns, programmer intent, coding conventions, or assumptions about omitted code.
# Reasonable interpretations of explicit control-flow conditions are allowed, but every reported validation must be directly supported by the provided code context.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ## 20260630-2 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please explicitly perform and report the following analysis procedure before producing the final result. The analyses of Steps 1 and 2 are required parts of the response and must not be omitted, even if the final answer appears straightforward.
# Analysis Requirements
# Perform the analysis sequentially according to the steps below.
# Each step depends on the result of the previous step and must not be skipped, merged, or reordered.
# Specifically:
# - Step 1 must identify the critical variable and explain why it is selected.
# - Step 2 must evaluate only the critical variable identified in Step 1 and report the supporting evidence.
# - Step 3 must summarize the conclusions from Steps 1 and 2 without introducing new analysis.
# Once the critical variable has been identified in Step 1, do not redefine, replace, or refine it during later steps.
# Step-by-Step Analysis Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the critical variable solely based on the targeted line. The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# For chained pointer-member accesses (e.g., `neigh->dev->dev_addr`, `ctx->ops->read`, `skb->dev->mtu`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `neigh->dev`, `ctx->ops`, `skb->dev`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# After identifying the critical variable, determine whether it originates from a formal parameter. If so, identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context.
# A valid check must satisfy all of the following:
# * The condition explicitly involves the critical variable identified in Step 1, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation must be supported by explicit evidence in the provided source code context.
# Do not conclude that the critical variable has been checked solely based on function semantics, prior usage, subsystem-specific programming patterns, programmer intent, coding conventions, or assumptions about omitted code.
# Reasonable interpretations of explicit control-flow conditions are allowed, but every reported validation must be directly supported by the provided source code context.
# If no explicit evidence satisfying the above criteria exists in the provided code context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Do not introduce new evidence, identify a new critical variable, or revise the conclusions from previous steps.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

# ## 20260704 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Analysis Instructions:
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Inter-procedural analysis:
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", identify the critical variable through a joint analysis of the targeted line, the provided callsite, and the parameter-passing relationship together with the surrounding code context. Do not determine the critical variable solely from the targeted line or callsite statetment.
# The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# When analyzing the targeted line:
# - For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# - For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# During the joint analysis, use the provided callsite and the parameter-passing relationship to determine which object at the callsite corresponds to the object required by the targeted line. Consider both the callee-side usage and the caller-side argument together to identify the actual critical object across the function boundary. Whenever applicable, express the identified critical variable using the corresponding callsite argument.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# • Intra-procedural analysis:
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line or, when Parameter Annotation is Yes, the corresponding callsite argument.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The control-flow predicate must directly evaluate the critical variable identified in Step 1. 
# - The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check. Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code. If no code pattern satisfying all of the above requirements exists in the provided context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format:
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

# ## 20260705 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Analysis Instructions:
# Step 1: Determine the analysis mode and identify the critical variable.
# A critical variable is the variable whose correctness or validity is required for the safe execution of the targeted line (e.g., pointers, error codes, status flags).
# If Parameter Annotation is "Yes", identify the critical variable through a joint analysis of the targeted line, the provided callsite, and the parameter-passing relationship together with the surrounding code context. Do not determine the critical variable solely from the targeted line or callsite statetment.
# The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# When analyzing the targeted line:
# - For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# - For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# During the joint analysis, use the provided callsite and the parameter-passing relationship to determine which object at the callsite corresponds to the object required by the targeted line. Consider both the callee-side usage and the caller-side argument together to identify the actual critical object across the function boundary. Whenever applicable, express the identified critical variable using the corresponding callsite argument.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line or, when Parameter Annotation is Yes, the corresponding callsite argument.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The control-flow predicate must directly evaluate the critical variable identified in Step 1. 
# - The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check. Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code. If no code pattern satisfying all of the above requirements exists in the provided context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format:
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

## 20260706 (+STC with full_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Analysis Instructions:
# Step 1: Determine the analysis mode and identify the critical variable.
# First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
# • Inter-procedural analysis:
# If both Caller Function and Callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", identify the formal parameter used at the targeted line and determine its corresponding argument at the provided callsite. Treat them as representing the same critical variable across the function boundary, and report the corresponding callsite argument as the critical variable.
# Otherwise, determine the critical variable directly from the targeted line according to its statement type using the same rules as the intra-procedural analysis.
# • Intra-procedural analysis:
# If Caller Function or Callsite is unavailable, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# For pointer dereference expressions:
# - For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# - For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
# If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The control-flow predicate must directly evaluate the critical variable identified in Step 1.
# - The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# - The other branch continues normal execution.
# A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check.
# Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context.
# Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the identified critical variable is a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format:
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

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
For pointer dereference expressions:
- For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
- For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
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

# ## 20260630 (+STC+PCCE with classify_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the object whose validity is required for the safe execution of the targeted line.
# If the targeted line directly accesses a formal parameter or one of its members (e.g., `dev`, `dev->name`), treat the formal parameter (e.g., `dev`) as the critical variable.
# If the targeted line contains chained pointer-member accesses (e.g., `dev->name->addr`), identify the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# Then identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation may appear anywhere within the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
# Only consider validations that occur **before the first potentially unsafe use** of the critical variable.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ## 20260630-1 (+STC+PCCE with classify_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Reasoning Requirements
# Perform the analysis sequentially according to the steps below.
# Each step depends on the result of the previous step and must not be skipped, merged, or reordered.
# Specifically:
# - Step 1 identifies the critical variable.
# - Step 2 evaluates only the critical variable identified in Step 1.
# - Step 3 produces the final result based solely on the conclusions from Steps 1 and 2.
# Once the critical variable has been identified in Step 1, do not redefine, replace, or refine it during later steps.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the critical variable solely based on the targeted line. The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# After identifying the critical variable, determine whether it originates from a formal parameter. If so, identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation must be supported by explicit evidence in the provided source code context.
# Do not conclude that the critical variable has been checked solely based on function semantics, prior usage, subsystem-specific programming patterns, programmer intent, coding conventions, or assumptions about omitted code.
# Reasonable interpretations of explicit control-flow conditions are allowed, but every reported validation must be directly supported by the provided code context.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ## 20260630-2 (+STC+PCCE with classify_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please explicitly perform and report the following analysis procedure before producing the final result. The analyses of Steps 1 and 2 are required parts of the response and must not be omitted, even if the final answer appears straightforward.
# Analysis Requirements
# Perform the analysis sequentially according to the steps below.
# Each step depends on the result of the previous step and must not be skipped, merged, or reordered.
# Specifically:
# - Step 1 must identify the critical variable and explain why it is selected.
# - Step 2 must evaluate only the critical variable identified in Step 1 and report the supporting evidence.
# - Step 3 must summarize the conclusions from Steps 1 and 2 without introducing new analysis.
# Once the critical variable has been identified in Step 1, do not redefine, replace, or refine it during later steps.
# Step-by-Step Analysis Instructions
# Step 1: Determine the analysis mode and identify the critical variable.
# First determine whether the analysis is intra-procedural or inter-procedural.
# • Intra-procedural analysis
# If no caller function or callsite is provided, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# • Inter-procedural analysis
# If both caller function and callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", first identify the critical variable solely based on the targeted line. The critical variable is the object whose validity is required for the safe execution of the targeted line, rather than necessarily the formal parameter itself.
# For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# For chained pointer-member accesses (e.g., `neigh->dev->dev_addr`, `ctx->ops->read`, `skb->dev->mtu`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `neigh->dev`, `ctx->ops`, `skb->dev`) as the critical variable, rather than the outermost formal parameter or the final accessed member.
# After identifying the critical variable, determine whether it originates from a formal parameter. If so, identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding callsite argument as representing the same object across the function boundary. Express the identified critical variable using the corresponding callsite argument whenever applicable.
# If Parameter Annotation is "No", identify the critical variable directly from the targeted line according to the same rules as the intra-procedural analysis.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The predicate of the control-flow condition explicitly evaluates the critical variable identified in Step 1, or its corresponding variable at the provided callsite if Parameter Annotation is Yes. The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., return, goto error, break).
# - The other branch continues normal execution.
# A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check. Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code. If no code pattern satisfying all of the above requirements exists in the provided context, conclude that the critical variable has not been checked.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",

# ## 20260706 (+STC+PCCE with classify_code_contexts)
# f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Analysis Instructions:
# Step 1: Determine the analysis mode and identify the critical variable.
# First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
# • Inter-procedural analysis:
# If both Caller Function and Callsite are provided, perform an inter-procedural analysis.
# If Parameter Annotation is "Yes", identify the formal parameter used at the targeted line and determine its corresponding argument at the provided callsite. Treat them as representing the same critical variable across the function boundary, and report the corresponding callsite argument as the critical variable.
# Otherwise, determine the critical variable directly from the targeted line according to its statement type using the same rules as the intra-procedural analysis.
# • Intra-procedural analysis:
# If Caller Function or Callsite is unavailable, perform an intra-procedural analysis.
# Determine the critical variable according to the targeted line type:
# - Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., `read`, `rd32`, `copy_from_user`, `kmalloc`, `mutex_lock_interruptible`), treat the return value or the assigned variable as the critical variable.
# - Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# - Array operation:
# Treat the array index variable as the critical variable.
# - Other types:
# Select the most semantically significant variable whose correctness or validity is required for the safe execution of the targeted line.
# For pointer dereference expressions:
# - For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
# - For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
# If multiple candidate critical variables are identified, select only the one that is most directly associated with the targeted line. When Parameter Annotation is "Yes", prefer the corresponding callsite argument as the reported critical variable.
# Step 2: Using the critical variable identified in Step 1, determine whether it is validated in the provided code context according to the definition of a safety check.
# A valid safety check must satisfy all of the following requirements:
# - The control-flow predicate must directly evaluate the critical variable identified in Step 1.
# - The condition must determine the validity, state, or correctness of the critical variable itself, rather than another variable or expression.
# - The check introduces two distinct execution branches.
# - One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# - The other branch continues normal execution.
# A condition that only determines whether a statement using the critical variable is executed, while evaluating a different variable or expression, is not a safety check.
# The analysis must be performed solely on the provided code context and follow the above definition of a safety check.
# Every reported safety check must be directly supported by explicit control-flow evidence in the provided source code.
# Step 3: Based solely on the analyses and conclusions from Steps 1 and 2, provide the final result.
# Important:
# Your analysis must be based only on the provided source code context.
# Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the identified critical variable is a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Required Response Format:
# Step 1 Analysis:
# - Analysis Mode:
# - Critical Variable:
# - Reason:
# Step 2 Analysis:
# - Validation:
# - Supporting Evidence:
# - Reason:
# Final Result:
# Critical Variable: <name or none>
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">
# Evidence: <line(s) where the check occurs or explanation>
# Please strictly follow the above response format. Do not omit Step 1 Analysis or Step 2 Analysis. Do not use any other format.""",


## 20260707 (+STC+PCCE with classify_code_contexts)
f"""Analyze the Linux kernel code and determine whether the critical variable is validated with the targeted line and the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Analysis Instructions:
Step 1: Determine the analysis mode and identify the critical variable.
First, determine whether the analysis is intra-procedural or inter-procedural according to the provided code information.
• Inter-procedural analysis:
If both Caller Function and Callsite are provided, If both Caller Function and Callsite are provided, perform an inter-procedural analysis by treating the mapped parameter and argument as the same critical variable and analyzing whether this critical variable is explicitly validated anywhere along the execution path before the targeted line is reached.
If Parameter Annotation is "Yes", identify the formal parameter used at the targeted line and determine its corresponding argument at the provided callsite. Treat them as representing the same critical variable across the function boundary, and report the corresponding callsite argument as the critical variable.
Otherwise, determine the critical variable directly from the targeted line according to its statement type using the same rules as the intra-procedural analysis.
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
For pointer dereference expressions:
- For a simple member access (e.g., `dev->name`), treat the base pointer object (e.g., `dev`) as the critical variable.
- For chained pointer-member accesses (e.g., `dev->name->addr`), treat the nearest pointer expression whose validity is required before accessing the final member (e.g., `dev->name`) as the critical variable.
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


### +STC+PCCE prompt (20260629)
# f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions
# Step 1: Determine the critical variable depending on the targeted line.
# A critical variable is the variable (e.g., a pointer, error code, or status flag) whose correctness or validity is required for the safe execution of the targeted line.
# Determine the critical variable according to the targeted line type:
# • Function call with return value:
# If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible), treat the return value or the assigned variable as the critical variable.
# • Function call without return value:
# Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
# • Array operation:
# Treat the array index variable as the critical variable.
# • Other types:
# Select the most semantically significant variable whose correctness is required for the safe execution of the targeted line.
# If caller information is provided, perform an inter-procedural analysis by jointly considering the targeted line and the corresponding callsite.
# If Parameter Annotation is "Yes", the identified critical variable is a formal parameter of the enclosing function. Identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding argument as representing the same critical variable across the function boundary.
# Step 2: Examine whether the critical variable is validated in the provided code context.
# A valid check must satisfy **all** of the following:
# * The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
# * The check introduces two distinct execution branches.
# * One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
# * The other branch continues normal execution.
# The validation may appear anywhere within the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
# Only consider validations that occur **before the first potentially unsafe use** of the critical variable.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Parameter Annotation: {parameter_annotation}
# Indicates whether the targeted line uses a formal parameter of the enclosing function.
# Caller Function: {caller_function}
# The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
# Callsite: {callsite}
# The corresponding function call statement in the caller. If unavailable, ignore this field.
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
# Evidence: <"The line(s) where the check occurs or explanation">,
# Please strictly follow the above format. Do not use any other format.""",

# ### no_line_type prompt (20251106)
# f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions:
# Step 1: Determine the *critical variable* depending on the targeted line:
# A critical variable is any variable(e.g., pointers, function return values, error codes, status flags, offsets) used at the targeted line. 
# Step 2: Examine whether the critical variable is validated in the code context:
# A valid check must satisfy all of the following:
# The condition explicitly involves the critical variable.
# The check introduces two distinct branches:
# One branch must terminate or handle the error (e.g., return, goto error).
# The other branch continues normal execution.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.""", 

### add function labels prompt (20260629) (+STC+PCCE+FLG)
f"""Analyze the Linux kernel code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
Please follow a structured step-by-step reasoning process before giving the final answer.
Step-by-Step Reasoning Instructions
Step 1: Determine the critical variable depending on the targeted line.
A critical variable is the variable (e.g., a pointer, error code, or status flag) whose correctness or validity is required for the safe execution of the targeted line.
Determine the critical variable according to the targeted line type:
• Function call with return value:
If the line involves a function call that returns a value—whether the return value is directly used in an expression or assigned to a variable—and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible), treat the return value or the assigned variable as the critical variable.
• Function call without return value:
Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived purely from kernel-internal computations are generally not considered critical variables.
• Array operation:
Treat the array index variable as the critical variable.
• Other types:
Select the most semantically significant variable whose correctness is required for the safe execution of the targeted line.
If caller information is provided, perform an inter-procedural analysis by jointly considering the targeted line and the corresponding callsite.
If Parameter Annotation is "Yes", the identified critical variable is a formal parameter of the enclosing function. Identify the corresponding argument at the provided callsite and treat the formal parameter and the corresponding argument as representing the same critical variable across the function boundary.
If caller information is not provided and the additional information is not null, use it to identify the critical variable.
Step 2: Examine whether the critical variable is validated in the provided code context.
A valid check must satisfy **all** of the following:
* The condition explicitly involves the critical variable, or its corresponding callsite argument if Parameter Annotation is "Yes".
* The check introduces two distinct execution branches.
* One branch performs error handling or terminates execution (e.g., `return`, `goto error`, `break`).
* The other branch continues normal execution.
The validation may appear anywhere within the provided source code context, including both the callee-side code surrounding the targeted line and the caller-side code surrounding the provided callsite.
Only consider validations that occur **before the first potentially unsafe use** of the critical variable.
Step 3: Provide the analysis result according to the specified output format.
Important: Your analysis must be based **only** on the provided source code context. Do **not** make assumptions or speculative inferences about validation.
Code Information:
File Path: {file}
Targeted Line Number: {number}
Targeted Line Code: {code}
Targeted Line Type: {type}
Parameter Annotation: {parameter_annotation}
Indicates whether the targeted line uses a formal parameter of the enclosing function.
Caller Function: {caller_function}
The function that directly invokes the function containing the targeted line. If unavailable, ignore this field.
Callsite: {callsite}
The corresponding function call statement in the caller. If unavailable, ignore this field.
Source Code Context: {code_context}
Additional Information: {function_label_info}
Output Format:
Critical Variable: <name or none>,
Check Status: <"The critical variable has been checked" or "The critical variable has not been checked">,
Evidence: <"The line(s) where the check occurs or explanation">,
Please strictly follow the above format. Do not use any other format.""",



# ## few-shots baseline
# f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions:
# Step 1: Determine the *critical variable* depending on the targeted line:
# A critical variable is any variable(e.g., pointers, error codes, status flags) used at the targeted line.
# Step 2: Examine whether the critical variable is validated in the code context:
# A valid check must satisfy all of the following:
# The condition explicitly involves the critical variable. The check introduces two distinct branches: One branch must terminate or handle the error (e.g., return, goto error). The other branch continues normal execution.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Source Code Context: {code_context}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.
# Example 1:
# {{
# "File Path": "linux-4.20-rc5/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c",
# "Targeted Line Number": 14040,
# "Targeted Line Code": "rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);",
# "Source Code Context": ['doorbell_size);//##14030', '}}//##14031', 'if (!bp->doorbells) {{//##14032', 'dev_err(&bp->pdev->dev,//##14033', '"Cannot map doorbell space, aborting\\n");//##14034', 'rc = -ENOMEM;//##14035', 'goto init_one_freemem;//##14036', '}}}}//##14037', '//##14038', 'if (IS_VF(bp)) {{{{//##14039', 'rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);//##14040', 'if (rc)//##14041', 'goto init_one_freemem;//##14042', '//##14043', '#ifdef CONFIG_BNX2X_SRIOV//##14044', '/* VF with OLD Hypervisor or old PF do not support filtering *///##14045', 'if (bp->acquire_resp.pfdev_info.pf_cap & PFVF_CAP_VLAN_FILTER) {{{{//##14046', 'dev->hw_features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14047', 'dev->features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14048', '}}}}//##14049', '#endif//##14050'],
# "Output":
# Critical Variable: rc,
# Check Status: The critical variable has been checked,
# Evidence: Lines 14041-14042: "if (rc) goto init_one_freemem;" which branches to error handling on nonzero rc, while normal execution continues otherwise.
# }},
# Example 2:
# {{
# "File Path": "linux-4.20-rc5/drivers/rtc/rtc-ds1374.c",
# "Targeted Line Number": 449,
# "Targeted Line Code": "ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);",
# "Source Code Context": ['//##439', 'static void ds1374_wdt_disable(void)//##440', '{{{{//##441', 'int ret = -ENOIOCTLCMD;//##442', 'int cr;//##443', '//##444', 'cr = i2c_smbus_read_byte_data(save_client, DS1374_REG_CR);//##445', '/* Disable watchdog timer *///##446', 'cr &= ~DS1374_REG_CR_WACE;//##447', '//##448', 'ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);//##449', '}}}}//##450', '//##451', '/*//##452', '* Watchdog device is opened, and watchdog starts running.//##453', '*///##454', 'static int ds1374_wdt_open(struct inode *inode, struct file *file)//##455', '{{{{//##456', 'struct ds1374 *ds1374 = i2c_get_clientdata(save_client);//##457', '//##458', 'if (MINOR(inode->i_rdev) == WATCHDOG_MINOR) {{{{//##459'],
# "Output":
# Critical Variable: ret,
# Check Status: The critical variable has not been checked,
# Evidence: At line 449, ret is assigned from i2c_smbus_write_byte_data(...). The next line (450) closes the block, and there is no conditional check involving ret (e.g., if (ret < 0) …) in the provided context.
# }},
# Example 3:
# {{
# "File Path": "linux-4.20-rc5/drivers/media/dvb-frontends/stv090x.c",
# "Targeted Line Number": 1456,
# "Targeted Line Code": "STV090x_WRITE_DEMOD(state, CARCFG, 0x46);",
# "Source Code Context": ['/* >= Cut 3 *///##1446', 'if (state->srate <= 5000000) {{{{//##1447', '/* enlarge the timing bandwidth for Low SR *///##1448', 'STV090x_WRITE_DEMOD(state, RTCS2, 0x68);//##1449', '}} else {{{{//##1450', '/* reduce timing bandwidth for high SR *///##1451', 'STV090x_WRITE_DEMOD(state, RTCS2, 0x44);//##1452', '}}}}//##1453', '//##1454', '/* Set CFR min and max to manual mode *///##1455', 'STV090x_WRITE_DEMOD(state, CARCFG, 0x46);//##1456', '//##1457', 'if (state->algo == STV090x_WARM_SEARCH) {{{{//##1458', '/* WARM Start//##1459', '* CFR min = -1MHz,//##1460', '* CFR max = +1MHz//##1461', '*///##1462', 'freq_abs  = 1000 << 16;//##1463', 'freq_abs /= (state->internal->mclk / 1000);//##1464', 'freq      = (s16) freq_abs;//##1465', '}} else {{{{//##1466'],
# "Output":
# Critical Variable: state,
# Check Status: The critical variable has not been checked,
# Evidence: The only condition in the provided context is "if (state->srate <= 5000000) {{ ... }} else {{ ... }}" (lines 1447–1453), which adjusts settings based on state->srate and does not validate the 'state' pointer nor introduce an error-handling branch. No explicit check (e.g., NULL check or error path) involving 'state' is present before the targeted line.
# }},
# Example 4:
# {{
# "File Path": "linux-4.20-rc5/drivers/md/dm-ioctl.c",
# "Targeted Line Number": 1765,
# "Targeted Line Code": "memcpy(dmi, param_kernel, minimum_data_size);",
# "Source Code Context": ['//##1755', 'if (!dmi) {{//##1756', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1757', 'return -EFAULT;//##1758', 'return -ENOMEM;//##1759', '}}//##1760', '//##1761', '*param_flags |= DM_PARAMS_MALLOC;//##1762', '//##1763', '/* Copy from param_kernel (which was already copied from user) *///##1764', 'memcpy(dmi, param_kernel, minimum_data_size);//##1765', '//##1766', 'if (copy_from_user(&dmi->data, (char __user *)user + minimum_data_size,//##1767', 'param_kernel->data_size - minimum_data_size))//##1768', 'goto bad;//##1769', 'data_copied://##1770', '/* Wipe the user buffer so we do not return it to userspace *///##1771', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1772', 'goto bad;//##1773', '//##1774', '*param = dmi;//##1775'],
# "Output":
# Critical Variable: dmi,
# Check Status: The critical variable has been checked,
# Evidence: The check occurs at line 1755 where `if (!dmi)` evaluates the critical variable dmi, and if it is NULL, the function returns -ENOMEM at line 1758, which represents error handling. This satisfies the requirement of a valid check with two distinct branches: one for error handling (return -ENOMEM) and another for normal execution (continuing past the if block).
# }}""",

# ## few-shots + LLMSA-MC
# f"""Analyze the Linux kernel v4.20-rc5 code and determine whether the critical variable of the targeted line is validated with the provided code context (based on annotated line numbers).
# Please follow a structured step-by-step reasoning process before giving the final answer.
# Step-by-Step Reasoning Instructions:
# Step 1: Determine the *critical variable* depending on the type of the targeted line and any available additional information:
# - **Function call with return value:**
#   If the line involves a function call that returns a value — whether the return value is directly used in an expression or assigned to a variable — and the function is known or likely to produce externally influenced, hardware-derived, or error-indicating results (e.g., read, rd32, copy_from_user, kmalloc, mutex_lock_interruptible),
# then treat the return value or the assigned variable as the critical variable.
#   - **Function call without return value:**
#   Treat parameters that may originate from external or user-controlled sources as critical variables. Parameters derived from purely kernel-internal computations are generally *not* considered critical variables.
# - **Array operation:**
#   The array index variable is the critical variable.
# - **Other types:**
#   Select the most semantically significant variable that could affect safety or correctness as the critical variable.
# If the additional information is not null, use it to identify the critical variable.
# Step 2: Examine whether the critical variable is validated in the code context:
# A valid check must satisfy all of the following:
# The condition explicitly involves the critical variable.
# The check introduces two distinct branches:
# One branch must terminate or handle the error (e.g., return, goto error).
# The other branch continues normal execution.
# Step 3: Provide the analysis result according to the specified output format.
# Important: Your analysis must be based on the provided code context. Do not make assumptions or speculative inferences about validation.
# Code Information:
# File Path: {file}
# Targeted Line Number: {number}
# Targeted Line Code: {code}
# Targeted Line Type: {type}
# Source Code Context: {code_context}
# Additional Information: {function_label_info}
# Output Format:
# Critical Variable: <name or none>,
# Check Status: <'The critical variable has been checked' or 'The critical variable has not been checked'>,
# Evidence: <'The line(s) where the check occurs or explanation'>,
# Please strictly follow the above format. Do not use any other format.
# Example 1:
# {{
# "File Path": "linux-4.20-rc5/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c",
# "Targeted Line Number": 14040,
# "Targeted Line Code": "rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);",
# "Targeted Line Type": "Returning Function Call",
# "Source Code Context": ['rc = bnx2x_vfpf_acquire(bp, tx_count, rx_count);//##14040','if (rc)//##14041','goto init_one_freemem;//##14042','//##14043','#ifdef CONFIG_BNX2X_SRIOV//##14044','/* VF with OLD Hypervisor or old PF do not support filtering *///##14045','if (bp->acquire_resp.pfdev_info.pf_cap & PFVF_CAP_VLAN_FILTER) {{{{//##14046','dev->hw_features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14047','dev->features |= NETIF_F_HW_VLAN_CTAG_FILTER;//##14048','}}}}//##14049'],
# "Output":
# Critical Variable: rc,
# Check Status: The critical variable has been checked,
# Evidence: Lines 14041-14042: "if (rc) goto init_one_freemem;" which branches to error handling on nonzero rc, while normal execution continues otherwise.
# }},
# Example 2:
# {{
# "File Path": "linux-4.20-rc5/drivers/rtc/rtc-ds1374.c",
# "Targeted Line Number": 449,
# "Targeted Line Code": "ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);",
# "Targeted Line Type": "Returning Function Call",
# "Source Code Context": ['ret = i2c_smbus_write_byte_data(save_client, DS1374_REG_CR, cr);//##449','}}}}//##450','//##451','/*//##452','* Watchdog device is opened, and watchdog starts running.//##453','*///##454','static int ds1374_wdt_open(struct inode *inode, struct file *file)//##455','{{{{//##456','struct ds1374 *ds1374 = i2c_get_clientdata(save_client);//##457','//##458'],
# "Output":
# Critical Variable: ret,
# Check Status: The critical variable has not been checked,
# Evidence: At line 449, ret is assigned from i2c_smbus_write_byte_data(...). The next line (450) closes the block, and there is no conditional check involving ret (e.g., if (ret < 0) …) in the provided context.
# }},
# Example 3:
# {{
# "File Path": "linux-4.20-rc5/drivers/media/dvb-frontends/stv090x.c",
# "Targeted Line Number": 1456,
# "Targeted Line Code": "STV090x_WRITE_DEMOD(state, CARCFG, 0x46);",
# "Targeted Line Type": "Void Function Call",
# "Source Code Context": "['/* >= Cut 3 *///##1446','if (state->srate <= 5000000) //##1447','/* enlarge the timing bandwidth for Low SR *///##1448','STV090x_WRITE_DEMOD(state, RTCS2, 0x68);//##1449','else {{{{//##1450','/* reduce timing bandwidth for high SR *///##1451','STV090x_WRITE_DEMOD(state, RTCS2, 0x44);//##1452','}}}}//##1453','//##1454','/* Set CFR min and max to manual mode *///##1455']",
# "Output":
# Critical Variable: state,
# Check Status: The critical variable has not been checked,
# Evidence: The only condition in the provided context is "if (state->srate <= 5000000) {{ ... }} else {{ ... }}" (lines 1447–1453), which adjusts settings based on state->srate and does not validate the 'state' pointer nor introduce an error-handling branch. No explicit check (e.g., NULL check or error path) involving 'state' is present before the targeted line.
# }},
# Example 4:
# {{
# "File Path": "linux-4.20-rc5/drivers/md/dm-ioctl.c",
# "Targeted Line Number": 1765,
# "Targeted Line Code": "memcpy(dmi, param_kernel, minimum_data_size);",
# "Targeted Line Type": "Void Function Call",
# "Source Code Context": "['//##1755', 'if (!dmi) {{//##1756', 'if (secure_data && clear_user(user, param_kernel->data_size))//##1757', 'return -EFAULT;//##1758', 'return -ENOMEM;//##1759', '}}//##1760', '//##1761', '*param_flags |= DM_PARAMS_MALLOC;//##1762', '//##1763', '/* Copy from param_kernel (which was already copied from user) *///##1764']",
# "Output":
# Critical Variable: dmi,
# Check Status: The critical variable has been checked,
# Evidence: The check occurs at line 1755 where `if (!dmi)` evaluates the critical variable dmi, and if it is NULL, the function returns -ENOMEM at line 1758, which represents error handling. This satisfies the requirement of a valid check with two distinct branches: one for error handling (return -ENOMEM) and another for normal execution (continuing past the if block).
# }}"""
]


def parse_line(line):
    """
    解析行数据，支持不同数据类型的文件格式

    对于 mc_cross 数据类型，使用新格式（8 字段）：
        file_path ;; line_no ;; targeted_line_code ;; caller_function ;; callsite ;; context ;; type ;; parameter_annotation

    对于其他数据类型，支持标准格式（5 字段）：
        file_path ;; line_no ;; line_code ;; context ;; type
    """
    parts = line.strip().split(" ;; ")
    start_idx = 0

    # 提取基本字段
    abs_path = parts[start_idx].strip()
    rel_path = abs_path.replace("../data/kernel-code/", "")
    file_path = rel_path

    line_no = parts[start_idx + 1].strip() if len(parts) > start_idx + 1 else ""

    # 检查是新格式（8 字段）还是旧格式（5 字段）
    if len(parts) >= 8:
        # 新的 mc_cross 格式
        targeted_line_code = parts[start_idx + 2].strip() if len(parts) > start_idx + 2 else ""
        caller_function = parts[start_idx + 3].strip() if len(parts) > start_idx + 3 else ""
        callsite_code = parts[start_idx + 4].strip() if len(parts) > start_idx + 4 else ""
        context_code = parts[start_idx + 5].strip() if len(parts) > start_idx + 5 else ""
        raw_type = parts[start_idx + 6].strip() if len(parts) > start_idx + 6 else ""
        parameter_annotation = parts[start_idx + 7].strip() if len(parts) > start_idx + 7 else "No"
        return file_path, line_no, targeted_line_code, caller_function, callsite_code, context_code, raw_type, parameter_annotation
    else:
        # 旧格式（兼容其他数据类型）
        line_code = parts[start_idx + 2].strip() if len(parts) > start_idx + 2 else ""
        context_code = parts[start_idx + 3].strip() if len(parts) > start_idx + 3 else ""
        raw_type = parts[start_idx + 4].strip() if len(parts) > start_idx + 4 else ""
        parameter_annotation = parts[start_idx + 5].strip() if len(parts) > start_idx + 5 else "No"
        # 返回格式兼容性：返回 8 个值，但后面的是空的
        return file_path, line_no, line_code, "", "", context_code, raw_type, parameter_annotation


def is_responses_api_model(model):
    """检查模型是否使用 responses.create() API"""
    responses_models = ['DeepSeek-R1', 'Qwen3-Coder']
    return any(model_name in model for model_name in responses_models)

def test_api_connection(client, model):
    """测试与API的连接是否正常"""
    try:
        if is_responses_api_model(model):
            # 使用 responses.create() API
            response = client.responses.create(
                model=model,
                input="Say 'Hello' briefly",
                text={"verbosity": "low"}
            )
        else:
            # 使用 chat.completions.create() API
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
        return False

def save_prompt_log(data_type_name, prompt_type_name, model_name):
    """将收集的 prompt 日志保存到文件（如果启用）"""
    if not enable_prompt_log or not prompt_logs:
        return

    log_dir = f"../data/test_data/test_results_2026/{data_type_name}/{prompt_type_name}_{model_name}"
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
    分析提示的主函数
    参数说明：
    - dt: 数据类型索引 (0:mc, 1:sc, 2:bug_list_0.15, 3:mc_macro)
    - j: 提示类型索引 (0:COT0, 1:COT1, 2:COT2, 3:COT3, 4:Few-Shots, 5:Few-Shots+LLMSA-MC)
    - missing_ids: 要分析的样本 ID 列表 (1-based, 例如 [1, 2, 3, 5])。如果为 None，分析所有样本
    """

    # 根据prompt_type的索引，确定配置策略
    # COT0: naive prompt: type="", function_label_info="", 文件:classify_full_contexts.list
    # COT1: +STC prompt: type有值, function_label_info="", 文件:classify_full_contexts.list
    # COT2: +STC+PCCE prompt: type有值, function_label_info="", 文件:classify.list
    # COT3: +STC+PCCE+FLG prompt: type有值, function_label_info有值, 文件:classify.list
    # Few-Shots: 基础 few-shot 学习示例，使用 COT0 策略
    # Few-Shots1: 增强 few-shot 学习（含函数标签），使用 COT3 策略

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

    # 确定要读取的文件
    if use_full_contexts:
        list_file = f"../data/test_data/{data_type[dt]}_classify_full_contexts.list"
    else:
        list_file = f"../data/test_data/{data_type[dt]}_classify.list"

    # 如果需要使用function_labels，从对应的文件中读取
    function_labels = {}
    if use_function_labels:
        labels_file = f"../data/test_data/{data_type[dt]}_classify_function_labels.list"
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

    # 如果指定了 missing_ids，只分析这些样本（1-based转0-based）
    sample_indices = None
    if missing_ids:
        sample_indices = set(id - 1 for id in missing_ids)  # 转换为 0-based 索引

    # 设置并发数：missing_ids分析时使用max_workers=1（顺序执行），否则使用max_workers=8
    max_workers = 1 if missing_ids else 8
    max_workers = 1 if data_type[dt] == "mc_macro" else max_workers  # mc_macro数据集也使用顺序执行

    try:
        if not os.path.exists(list_file):
            return None

        with open(list_file, "r", encoding='utf-8') as f:
            lines = f.readlines()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(len(lines)):
                # 如果指定了样本 ID，只处理指定的样本
                if sample_indices is not None and i not in sample_indices:
                    continue

                try:
                    # 使用统一的解析函数
                    parse_result = parse_line(lines[i])

                    # 根据返回值的长度判断是新格式还是旧格式
                    if len(parse_result) == 8:
                        file_path, line_no, targeted_line_code, caller_function, callsite_code, context_code, raw_type, parameter_annotation = parse_result
                    else:
                        file_path, line_no, line_code, context_code, raw_type, parameter_annotation = parse_result[:6]
                        targeted_line_code = line_code
                        caller_function = ""
                        callsite_code = ""

                    # 根据策略决定是否使用type
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

                    # 根据策略决定是否使用function_label_info
                    function_label_info = ""
                    if use_function_labels:
                        seq_num = i + 1  # 将0-based索引转为1-based序号
                        if seq_num in function_labels:
                            label_value = function_labels[seq_num]
                            # 只有当标签值不是'0'时才使用
                            if label_value != '0':
                                function_label_info = label_value

                    # 转义包含花括号的变量，避免 .format() 错误
                    # build_prompts 需要：file, number, code, caller_function, callsite, code_context, type, function_label_info, parameter_annotation
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

            # 等待所有任务完成
            for sample_id, model, future in futures:
                try:
                    future.result(timeout=300)  # 单个任务超时 5 分钟
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

    # 设置全局日志开关
    globals()['enable_prompt_log'] = args.save_prompts

    client = OpenAI(
        base_url="https://aihubmix.com/v1",
        api_key="sk-zZa4lJoKCuiLtklk7913Ab1e6a74438e84C84c5b993e09F6",
    )

    # 模型在线状态映射（是否需要web_search_options）
    model_online_status = {
        'DeepSeek-V3': False,
        'qwen3-coder-480b-a35b-instruct': False,
        'llama-3.3-70b': False,
        # 'qwen3-coder-plus-2025-07-22': False,
        'gpt-4o': False,
        # 'DeepSeek-R1': False,
        # 'deepseek-r1': False,
        'claude-sonnet-4-20250514': False,
        # 'Qwen3-Coder': False,
        'qwen3-coder-plus': False,
        'gemini-2.5-pro': False,
    }

    # 使用全局定义的 data_type 和 prompt_type
    # data_type = {0: "mc", 1: "sc", 2: "bug_list_0.15", 3: "mc_macro"}
    # prompt_type = {0: 'RAW', 1: 'COT0', 2: 'COT', 3: 'COT1', 4: 'COT2', 5: 'COT3'}


    # 处理命令行参数 - 支持单个调试或批量处理
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

    # 在开始分析前测试 API 连接
    api_ok = False
    for model in model_list:
        if test_api_connection(client, model):
            api_ok = True
            break

    if not api_ok:
        print("[CRITICAL] API connection failed!")
        exit(1)

    # 遍历所有组合进行分析
    for dt in data_type_indices:
        for j in prompt_type_indices:
            for model in model_list:
                # 根据模型确定是否在线
                is_online_model = model_online_status.get(model, False)

                summary_rows.clear()

                # 调用llm_analysis进行分析
                elapsed_time = llm_analysis(client, [model], is_online_model, data_type, dir, dt=dt, j=j, missing_ids=args.missing_ids)

                # 为每个组合生成CSV结果
                output_csv = f"../data/test_data/test_results_2026/{data_type[dt]}_{dir[j]}_{model}_result.csv"
                os.makedirs(os.path.dirname(output_csv), exist_ok=True)

                # 如果是通过 missing_ids 分析补充的数据，追加到原始文件
                if args.missing_ids:
                    # 读取原始文件的内容（除去最后的时间统计行）
                    existing_rows = []
                    total_time = elapsed_time

                    if os.path.exists(output_csv):
                        with open(output_csv, "r", newline='', encoding="utf-8") as f:
                            reader = csv.reader(f)
                            for i, row in enumerate(reader):
                                if i == 0:  # 跳过标题行
                                    continue
                                # 跳过最后的时间统计行（通常包含 "Total analysis time"）
                                if row and len(row) > 0 and "Total analysis time" in str(row[0]):
                                    # 从这一行提取之前的分析时间
                                    time_str = str(row[0])
                                    # 尝试提取时间数值
                                    import re
                                    match = re.search(r'(\d+\.\d+)', time_str)
                                    if match:
                                        try:
                                            total_time += float(match.group(1))
                                        except:
                                            pass
                                else:
                                    existing_rows.append(row)

                    # 写入原始行 + 新行
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(existing_rows)
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV updated to {output_csv}")
                else:
                    # 正常情况：创建新文件
                    with open(output_csv, "w", newline='', encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Prompt_Type", "Sample_ID", "Model", "Result", "Output_File"])
                        writer.writerows(summary_rows)
                        writer.writerow([f"Total analysis time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)"])
                    print(f"✓ Summary CSV written to {output_csv}")

                # 保存 prompt 日志
                save_prompt_log(data_type[dt], dir[j], model)
                prompt_logs.clear()  # 清空日志列表以进行下一个组合