# -*- coding: utf-8 -*-
import os
import csv
from collections import defaultdict
from sklearn.metrics import precision_score, recall_score, f1_score
import itertools
import pandas as pd
from itertools import combinations
import re
import io
import sys
import regex

num_samples = 147

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_cv_map(cv_file_path):
    cv_map = {}
    with open(cv_file_path, 'r', encoding='utf-8') as cv_file:
        lines = cv_file.readlines()
        seq = 1
        for line in lines:
            cv_map[seq] = line.strip()
            seq += 1
    return cv_map


def check_missing_files(results_dir, start_id=1, end_id=147):
    """
    检查 results_dir 中是否存在指定范围内的所有样本文件（通过文件名中的ID）
    返回缺失的 ID 列表
    """
    existing_ids = set()

    # 扫描目录中的所有 .txt 文件
    for root, _, files in os.walk(results_dir):
        for f in files:
            if f.endswith(".txt"):
                try:
                    # 文件名格式: {model}_{id}_*.txt 或其他格式
                    # 尝试从文件名中提取数字
                    parts = f.split('_')
                    if len(parts) >= 2:
                        # 倒数第二个部分通常是样本 ID
                        sample_id = int(parts[-2])
                        existing_ids.add(sample_id)
                except (ValueError, IndexError):
                    pass

    # 找出缺失的 ID
    expected_ids = set(range(start_id, end_id + 1))
    missing_ids = sorted(expected_ids - existing_ids)

    return missing_ids

def extract_cv_from_llm_results(cv_map, results_dir, dt, output_file=None):
    # 匹配 "Critical Variable: ..." 的正则表达式，支持更复杂的表达式（函数调用、操作符等）
    # 支持格式：
    # - 纯文本：Critical Variable: var_name
    # - JSON："Critical Variable": "value" 或 "Critical Variable": "value",
    # - 简单变量：var_name
    # - 函数调用：function_name(arg1, arg2)
    # - 带操作符：return value, ->field 等
    # - 指针引用：msb->io_queue

    # 支持两种模式：
    # 1. JSON模式：\"Critical Variable\": \"value\" （值被引号包围，可包含逗号和其他特殊字符）
    # 2. 纯文本模式：Critical Variable: value （值直到行末或逗号）
    pattern = re.compile(
        r'(?:\*\*)?\s*"?Critical\s+Variable"?\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?\s*'
        r'(?:"([^"]*)"|([^,\n]+))'  # 两个捕获组：带引号的值 或 不带引号的值（贪心）
        r'(?:\s*[,\n]|$)',
        re.IGNORECASE
    )
    # pattern = re.compile(r"Critical\s+Variable\s*:", re.IGNORECASE)
    # 遍历所有 txt 文件

    # 如果没有指定输出文件，使用默认路径
    if output_file is None:
        output_file = results_dir+'_'+dt+'_cv_results.csv'

    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as write_file:
        for root, _, files in os.walk(results_dir):
            for f in files:
                # if f not in cv_match_results:
                #     cv_match_results[f] = []
                if f.endswith(".txt"):
                    sample_id = int(f.split('_')[-2])
                    # print(f, sample_id)
                    file_path = os.path.join(root, f)
                    # print(file_path, sample_id)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                        content_parts = content.split('\n')
                        target_line = ""
                        for line in content_parts:
                            line = line.strip()
                            match = pattern.search(line)
                            if match:
                                target_line += line 
                        # print(target_line)
                        if target_line:
                            # 提取变量名并清洗
                            # print("target_line: ", target_line)
                            cv = ""
                            cv_list = []

                            # 方法1：尝试从JSON格式提取 Critical Variable
                            # 支持格式：
                            # - "Critical Variable": "var_name" (JSON中)
                            # - "Output": { "Critical Variable": "var_name" } (嵌套JSON)
                            # - 复杂结构：包含数组、多层嵌套等
                            try:
                                import json
                                # 尝试解析为JSON
                                if '{' in target_line and '}' in target_line:
                                    # 策略1：尝试找到顶层JSON对象
                                    try:
                                        # 提取JSON对象（从第一个{到最后一个}）
                                        start_idx = target_line.find('{')
                                        if start_idx != -1:
                                            # 找到匹配的关闭括号
                                            brace_count = 0
                                            end_idx = -1
                                            for i in range(start_idx, len(target_line)):
                                                if target_line[i] == '{':
                                                    brace_count += 1
                                                elif target_line[i] == '}':
                                                    brace_count -= 1
                                                    if brace_count == 0:
                                                        end_idx = i
                                                        break

                                            if end_idx != -1:
                                                json_str = target_line[start_idx:end_idx+1]
                                                try:
                                                    json_obj = json.loads(json_str)
                                                    if isinstance(json_obj, dict):
                                                        # 检查Output嵌套
                                                        if 'Output' in json_obj and isinstance(json_obj['Output'], dict):
                                                            cv = json_obj['Output'].get('Critical Variable', '')
                                                        else:
                                                            cv = json_obj.get('Critical Variable', '')
                                                except json.JSONDecodeError:
                                                    pass
                                    except:
                                        pass

                            except:
                                pass

                            # 方法2：如果JSON解析失败，使用正则表达式提取（处理两个捕获组）
                            if not cv:
                                regex_match = pattern.search(target_line)
                                if regex_match:
                                    # 从两个捕获组中取非空的一个
                                    cv = regex_match.group(1) if regex_match.group(1) else regex_match.group(2)
                                    cv = cv.strip() if cv else ""

                                # 如果仍然没有提取到值，回退到冒号分割
                                if not cv:
                                    cv = target_line.split(":")[-1].strip()

                            # 清理cv字符串
                            cv = cv.rstrip(',"\'`.*\n')

                            # 使用正则提取所有可能的变量名和标识符
                            # 这包括函数名、参数名等、以及指针引用 (xxx->yyy)
                            # 首先尝试提取完整的指针引用 (xxx->yyy->zzz)
                            pointer_refs = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*(?:->[a-zA-Z_][a-zA-Z0-9_]*)+', cv)
                            identifiers = pointer_refs if pointer_refs else re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cv)

                            if identifiers:
                                # 如果找到标识符，使用它们作为候选变量
                                cv_list = identifiers
                            elif ' ' in cv:
                                # 降级处理：按空格分割
                                cv_list = cv.split(' ')
                            elif ',' in cv:
                                # 降级处理：按逗号分割
                                cv_list = cv.split(',')
                            else:
                                # 最后的降级处理：整个字符串作为一个变量
                                if cv.strip():
                                    cv_list.append(cv.strip())

                            # 清洗每个变量名
                            cv_list = [var.strip(",`.*").lstrip(",`.*") for var in cv_list if var.strip()]
                            ## 'svc`**'
                            # cv_list = [var.replace('.', '') for var in cv_list]
                            # vars_raw = match.group(1)
                            # vars_list = [v.strip() for v in re.split(r"[,，\s]+", vars_raw) if v.strip()]
                            # print(f"File: {f}")
                            # print("Critical Variables:", vars_list)
                            cv_map_list = []
                            if ' ' in cv_map[sample_id]:
                                cv_map_list = cv_map[sample_id].split(' ')
                            elif ',' in cv_map[sample_id]:
                                cv_map_list = cv_map[sample_id].split(',')
                            else:
                                cv_map_list.append(cv_map[sample_id].strip())
                            # cv_map_list = [var.replace(',', '') for var in cv_map_list]
                            cv_map_list = [var.strip(",`.*").lstrip(",`.*") for var in cv_map_list]
                            cv_flag = False
                            ### return value in cv_list
                            if 'return' in cv_list and 'value' in cv_list:
                                cv_flag = True 
                            for var in cv_list:
                                if var in cv_map_list:
                                    cv_flag = True
                                    break
                            if cv_flag:
                                write_file.write(str(sample_id)+':1'+'\n')
                                # cv_match_results[f].append(1)
                            else:
                                print(file_path, cv_list, cv_map_list)
                                write_file.write(str(sample_id)+':0'+'\n')
                                # cv_match_results[f].append(0)
                            ### for debug
                            # if results_dir == '../../data/test_data/mc_/COT_Qwen3-Coder' and sample_id == 8:
                            #     print("Debug***********************************")
                            #     print(results_dir+'_'+dt+'_cv_results.csv', file_path, cv_list, cv_map_list, cv_flag)
                        else:
                            print(content, sample_id)
                            write_file.write(str(sample_id)+':2'+'\n')
                        
def extract_cv_from_llm_results_bug_list(base_dir, results_dir):
    cv_map = {}
    with open(base_dir+'bug_list_0.15_classify.list', 'r', encoding='utf-8') as file:
        cv_lines = file.readlines()
        seq = 0
        for cv_line in cv_lines:
            cv_line = cv_line.strip()
            if ' ;; ' not in cv_line:
                continue
            seq += 1
            cv_parts = cv_line.split(" ;; ")
            target_line_code = cv_parts[2]
            line_type = cv_parts[4]
            if line_type == 'Returning Function Call' and '=' in target_line_code:
                target_parts = target_line_code.split('=')
                target_left = target_parts[0].strip()
                cv_map[seq] = target_left
            elif line_type == 'Void Function Call' and '(' in target_line_code and ')' in target_line_code:
                pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\((?P<args>(?:[^()]+|(?R))*)\)'
                match = regex.search(pattern, target_line_code)
                if match:
                    args_str = match.group("args")
                    cv_map[seq] = args_str
                else:
                    # print(target_line_code)
                    cv_map[seq] = target_line_code
            else:
                # print(target_line_code)
                cv_map[seq] = target_line_code
    # print(cv_map[1104])
    # 匹配 "Critical Variable: ..." 的正则表达式
    pattern = re.compile(r"(?:\*\*)?\s*Critical\s+Variable\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?\s*([`a-zA-Z0-9_\-\>\.\[\]\(\),\s]+)", re.IGNORECASE)
    # pattern = re.compile(r"Critical\s+Variable\s*:", re.IGNORECASE)
    # 遍历所有 txt 文件
    with open(results_dir+'_cv_results.csv', 'w', encoding='utf-8') as write_file:
        for root, _, files in os.walk(results_dir):
            for f in files:
                if f.endswith(".txt"):
                    sample_id = int(f.split('_')[-2])
                    # print(f, sample_id)
                    file_path = os.path.join(root, f)
                    # print(file_path, sample_id)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                        content_parts = content.split('\n')
                        target_line = ""
                        for line in content_parts:
                            line = line.strip()
                            match = pattern.search(line)
                            if match:
                                target_line += line 
                        # print(target_line)
                        if target_line:
                            # 提取变量名并清洗
                            # print("target_line: ", target_line)
                            cv = target_line.split(":")[-1]
                            cv_list = []
                            if ' ' in cv:
                                cv_list = cv.split(' ')
                            elif ',' in cv:
                                cv_list = cv.split(',')
                            else:
                                cv_list.append(cv.strip())
                            cv_list = [var.strip(",`.*").lstrip(",`.*") for var in cv_list]

                            # print('cv_map[sample_id]:', cv_map[sample_id], sample_id)
                            cv_map_list = []
                            if ',' in cv_map[sample_id]:
                                cv_map_list = cv_map[sample_id].split(',')
                            else:
                                cv_map_list.append(cv_map[sample_id].strip())
                            # cv_map_list = [var.replace(',', '') for var in cv_map_list]
                            cv_map_list = [var.strip(",`.*").lstrip(",`.*") for var in cv_map_list]
                            
                            cv_flag = False
                            ### return value in cv_list
                            if 'return' in cv_list and 'value' in cv_list:
                                cv_flag = True 
                            for var in cv_list:
                                if var in cv_map_list:
                                    cv_flag = True
                                    break
                            if cv_flag:
                                # print('1------', file_path, cv_list, cv_map_list)
                                write_file.write(str(sample_id)+':1'+'\n')
                                # cv_match_results[f].append(1)
                            else:
                                print('0------', file_path, cv_list, cv_map_list)
                                write_file.write(str(sample_id)+':0'+'\n')
                                # cv_match_results[f].append(0)
                            ### for debug
                            # if results_dir == '../../data/test_data/mc_/COT_Qwen3-Coder' and sample_id == 8:
                            #     print("Debug***********************************")
                            #     print(results_dir+'_'+dt+'_cv_results.csv', file_path, cv_list, cv_map_list, cv_flag)
                        else:
                            print('2------', content)
                            write_file.write(sample_id+':2'+'\n')
        

def extract_model_name(filename):
    """
    从文件名中提取模型名称，例如：
    sc_COT_gemini-2.5-pro_classify.csv -> gemini-2.5-pro
    """
    base = os.path.basename(filename)
    # 去掉开头的 mc_/sc_ 和结尾的 _classify.csv
    name = base.replace(".csv", "")
    parts = name.split("_")
    # 模型名一般是倒数第二个部分
    if len(parts) == 4: ## 带_classify  ## new prompt results
        return parts[-2]
    if len(parts) == 5: ## 带_classify_notype  ## new prompt 2 results
        return parts[-3]
    elif len(parts) == 3: ## 不带_classify  ## old prompt results
        return parts[-1]
    elif len(parts) == 6: ## 带_classify_full_contexts  ## old prompt 1 results
        return parts[-4]
    else:
        return "unknown"


def parse_files(input_dir, input_dir_cv, cot_type, selected_models=None):
    # 不同模型的预测数据
    model_results = defaultdict(lambda: {"y_true": [], "y_pred": []})
    # 每个模型预测正确的样本ID集合
    model_correct_samples = defaultdict(set)
    model_pos_correct = defaultdict(set)
    model_neg_correct = defaultdict(set)
    # 每个模型预测错误的样本ID集合
    model_wrong_samples = defaultdict(set)
    model_pos_wrong = defaultdict(set)
    model_neg_wrong = defaultdict(set)

    mc_cv_results = {}
    sc_cv_results = {}
    mc_cv_results['mc'] = {}
    sc_cv_results['sc'] = {}

    for fn in os.listdir(input_dir_cv):
        fp = os.path.join(input_dir_cv, fn)

        # 跳过目录和非 CSV 文件
        if not fn.endswith(".csv"):
            continue

        # 跳过非 CV 结果文件（新格式：COT0_Model_mc_cv_results.csv）
        if '_cv_results.csv' not in fn:
            continue

        # 从新的 CV 结果文件名中提取信息
        # 格式: COT0_DeepSeek-V3_mc_cv_results.csv
        try:
            parts = fn.replace('_cv_results.csv', '').split('_')
            if len(parts) >= 3:
                # 最后一个部分是数据类型 (mc 或 sc)
                dt = parts[-1]
                # 第一个部分是 COT 类型
                file_cot_type = parts[0]
                # 中间的部分是模型名称
                mn = '_'.join(parts[1:-1])  # 模型名称可能包含下划线

                # 只加载指定 COT 类型的 CV 结果
                if file_cot_type != cot_type:
                    continue

                # 如果指定了模型，只加载这些模型的 CV 结果
                if selected_models and mn not in selected_models:
                    continue

                cv_results = {}
                seq = 0
                with open(fp, 'r', encoding='utf-8') as f1:
                    lines = f1.readlines()
                    for line in lines:
                        line = line.strip().strip('\n')
                        line_parts = line.split(':')
                        if len(line_parts) == 2:
                            seq = int(line_parts[0])
                            cv_results[seq] = int(line_parts[1])

                if dt == 'mc':
                    mc_cv_results['mc'][mn] = cv_results
                elif dt == 'sc':
                    sc_cv_results['sc'][mn] = cv_results
        except Exception as e:
            print("[Warning] Failed to parse CV results from {}: {}".format(fn, e))
            continue
    # print(mc_cv_results['mc'])

    for filename in os.listdir(input_dir):
        if not (filename.startswith("mc_") or filename.startswith("sc_")):
            continue
        file_path = os.path.join(input_dir, filename)
        if not file_path.endswith(".csv"):
            continue

        # 提取文件中的 COT 类型
        # 文件名格式: mc_COT0_qwen3-coder-plus-2025-07-22_result.csv
        parts = filename.replace('_result.csv', '').split('_')
        if len(parts) < 3:
            continue

        file_cot_type = parts[1]  # COT0, COT1, COT2, COT3

        # 只处理指定 COT 类型的文件
        if file_cot_type != cot_type:
            continue

        model_name = extract_model_name(filename)

        # 如果指定了模型，只处理这些模型的结果
        if selected_models and model_name not in selected_models:
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                result = row.get("Result", "")
                sample_id = row.get("Sample_ID", "")
                if sample_id is None or sample_id == '':
                    continue
                # print(model_name, int(sample_id))

                # 正样本
                if filename.startswith("mc_"):
                    # 检查模型是否在 CV 结果中
                    if model_name not in mc_cv_results['mc']:
                        print(f"[Warning] Model '{model_name}' not found in mc_cv_results. Skipping {filename}")
                        continue

                    if result == "Has not been checked" and mc_cv_results['mc'][model_name][int(sample_id)] == 1:  # 正确
                        model_results[model_name]["y_pred"].append(1)
                        model_results[model_name]["y_true"].append(1)
                        model_correct_samples[model_name].add(f"mc_{sample_id}")
                        model_pos_correct[model_name].add(f"mc_{sample_id}")
                    # elif result == "Has been checked":  # 错误
                    else:
                        model_results[model_name]["y_pred"].append(0)
                        model_results[model_name]["y_true"].append(1)
                        model_wrong_samples[model_name].add(f"mc_{sample_id}")
                        model_pos_wrong[model_name].add(f"mc_{sample_id}")

                # 负样本
                elif filename.startswith("sc_"):
                    # 检查模型是否在 CV 结果中
                    if model_name not in sc_cv_results['sc']:
                        print(f"[Warning] Model '{model_name}' not found in sc_cv_results. Skipping {filename}")
                        continue

                    if result == "Has been checked" and sc_cv_results['sc'][model_name][int(sample_id)] == 1: # 正确
                        model_results[model_name]["y_pred"].append(0)
                        model_results[model_name]["y_true"].append(0)
                        model_correct_samples[model_name].add(f"sc_{sample_id}")
                        model_neg_correct[model_name].add(f"sc_{sample_id}")
                    # elif result == "Has not been checked":  # 错误
                    else:
                        model_results[model_name]["y_pred"].append(1)
                        model_results[model_name]["y_true"].append(0)
                        model_wrong_samples[model_name].add(f"sc_{sample_id}")
                        model_neg_wrong[model_name].add(f"sc_{sample_id}")

    return model_results, model_correct_samples, model_pos_correct, model_neg_correct, model_wrong_samples, model_pos_wrong, model_neg_wrong


# def parse_files(input_dir):
#     # 不同模型的预测数据
#     model_results = defaultdict(lambda: {"y_true": [], "y_pred": []})
#     # 每个模型预测正确的样本ID集合
#     model_correct_samples = defaultdict(set)
#     model_pos_correct = defaultdict(set)
#     model_neg_correct = defaultdict(set)

#     for filename in os.listdir(input_dir):
#         if not (filename.startswith("mc_") or filename.startswith("sc_")):
#             continue
#         file_path = os.path.join(input_dir, filename)
#         if not file_path.endswith(".csv"):
#             continue

#         model_name = extract_model_name(filename)

#         with open(file_path, "r", encoding="utf-8") as f:
#             reader = csv.DictReader(f)
#             for row in reader:
#                 result = row.get("Result", "")
#                 sample_id = row.get("Sample_ID", "")

#                 # 正样本
#                 if filename.startswith("mc_"):
#                     if result == "Has not been checked":  # 正确
#                         model_results[model_name]["y_pred"].append(1)
#                         model_results[model_name]["y_true"].append(1)
#                         model_correct_samples[model_name].add(f"mc_{sample_id}")
#                         model_pos_correct[model_name].add(f"mc_{sample_id}")
#                     elif result == "Has been checked":  # 错误
#                         model_results[model_name]["y_pred"].append(0)
#                         model_results[model_name]["y_true"].append(1)

#                 # 负样本
#                 elif filename.startswith("sc_"):
#                     if result == "Has been checked":  # 正确
#                         model_results[model_name]["y_pred"].append(0)
#                         model_results[model_name]["y_true"].append(0)
#                         model_correct_samples[model_name].add(f"sc_{sample_id}")
#                         model_neg_correct[model_name].add(f"sc_{sample_id}")
#                     elif result == "Has not been checked":  # 错误
#                         model_results[model_name]["y_pred"].append(1)
#                         model_results[model_name]["y_true"].append(0)

#     return model_results, model_correct_samples, model_pos_correct, model_neg_correct


def compute_metrics(y_true, y_pred):
    
    # 计算 TP, TN, FP, FN
    TP = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    TN = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    FP = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    FN = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
    return accuracy, precision, recall, f1, TP, TN

def display(model_results):
    # print("{:<20s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
    #     "Model", "Accuracy", "Precision", "Recall", "F1", "TP", "TN"
    # ))
    print("{:<20s} {:>10s} {:>10s} {:>10s} {:>10s}".format(
        "Model", "Accuracy", "Precision", "Recall", "F1"
    ))
    print("-" * 65)

    for model, data in model_results.items():
        y_true = data["y_true"]
        y_pred = data["y_pred"]
        if not y_true:
            continue
        # accuracy, precision, recall, f1, TP, TN = compute_metrics(y_true, y_pred)
        # print("{:<20s} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f} {:>8d} {:>8d}".format(
        #     model, accuracy, precision, recall, f1, TP, TN
        # ))   
        accuracy, precision, recall, f1, _, _ = compute_metrics(y_true, y_pred)
        print("{:<20s} {:>10.4f} {:>10.4f} {:>10.4f} {:>10.4f}".format(
            model, accuracy, precision, recall, f1
        ))

def function_label_refinement(label_file, model_results):
    labeled_model_results = model_results
    with open(label_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            id, label = line.strip().split(':')
            if label == '1':
                for name in labeled_model_results:
                    labeled_model_results[name]['y_pred'][int(id)-1] = 1
    return labeled_model_results

def compute_coverage(model_correct_samples):
    models = list(model_correct_samples.keys())
    coverage_matrix = pd.DataFrame(0.0, index=models, columns=models)

    for m1, m2 in itertools.product(models, models):
        s1 = model_correct_samples[m1]
        s2 = model_correct_samples[m2]
        if not s1:
            continue
        inter = len(s1 & s2)
        cov = inter / len(s1)  # m2 在 m1 的正确结果上的覆盖率
        coverage_matrix.loc[m1, m2] = cov

    return coverage_matrix

def compute_jaccard(model_correct_samples):
    """
    计算模型间的 Jaccard 相似度：
    J(A,B) = |A ∩ B| / |A ∪ B|
    """
    models = list(model_correct_samples.keys())
    print("\n=== Model-wise Jaccard Similarity (Correct Detection Overlap) ===\n")

    results = []
    for m1, m2 in combinations(models, 2):
        set1 = model_correct_samples[m1]
        set2 = model_correct_samples[m2]

        inter = len(set1 & set2)
        union = len(set1 | set2)
        jaccard = inter / union if union > 0 else 0.0

        results.append((m1, m2, jaccard))
        print(f"{m1} vs {m2}:  Jaccard = {jaccard:.4f}  (|∩|={inter}, |∪|={union})")

    return results

def compute_unique_detection_rate(model_correct_samples):
    """
    计算每个模型的 Unique Detection Rate (UDR)
    """
    all_detections = set().union(*model_correct_samples.values()) if model_correct_samples else set()
    udr_scores = {}

    for model_name, detections in model_correct_samples.items():
        others = set().union(*[v for k, v in model_correct_samples.items() if k != model_name])
        unique_detections = detections - others
        udr_scores[model_name] = len(unique_detections) / len(all_detections) if all_detections else 0.0

    return udr_scores

def compute_difference_matrices(model_correct_samples):
    """
    计算模型间差异性矩阵：
    - diff_count_matrix：差异样本数量
    - diff_ratio_matrix：差异比例 (差异样本数 / 并集样本数)
    """
    model_names = sorted(model_correct_samples.keys())
    diff_count_matrix = pd.DataFrame(index=model_names, columns=model_names)
    diff_ratio_matrix = pd.DataFrame(index=model_names, columns=model_names)

    for m1 in model_names:
        for m2 in model_names:
            if m1 == m2:
                diff_count_matrix.loc[m1, m2] = 0
                diff_ratio_matrix.loc[m1, m2] = 0.0
            else:
                set1 = model_correct_samples[m1]
                set2 = model_correct_samples[m2]
                diff = set1.symmetric_difference(set2)
                union = set1 | set2
                diff_count = len(diff)
                ratio = diff_count / len(union) if union else 0
                diff_count_matrix.loc[m1, m2] = diff_count
                diff_ratio_matrix.loc[m1, m2] = round(ratio, 3)

    return diff_count_matrix, diff_ratio_matrix

def compare_new_old_prompts(old_pos, old_neg, new_pos, new_neg):
    """
    比较相同模型在新旧 prompt 上的检测结果差异：
    - 新的多检测出的正样本数
    - 新的少检测出的正样本数
    - 新的多检测出的负样本数
    - 新的少检测出的负样本数
    """
    all_models = set(old_pos.keys()) | set(new_pos.keys())

    print("=== 新旧 Prompt 检测结果差异统计 ===")
    for model in sorted(all_models):
        old_pos_set = old_pos.get(model, set())
        old_neg_set = old_neg.get(model, set())
        new_pos_set = new_pos.get(model, set())
        new_neg_set = new_neg.get(model, set())

        # 差异计算
        pos_more = len(new_pos_set - old_pos_set)  # 新增正样本
        pos_less = len(old_pos_set - new_pos_set)  # 减少正样本
        neg_more = len(new_neg_set - old_neg_set)  # 新增负样本
        neg_less = len(old_neg_set - new_neg_set)  # 减少负样本

        print(f"模型 {model}:")
        print(f"  新增正样本数 (TP more): {pos_more}, {new_pos_set - old_pos_set}")
        print(f"  减少正样本数 (TP less): {pos_less}, {old_pos_set - new_pos_set}")
        print(f"  新增负样本数 (TN more): {neg_more}, {new_neg_set - old_neg_set}")
        print(f"  减少负样本数 (TN less): {neg_less}, {old_neg_set - new_neg_set}")
        print("-" * 60)
        
def display_model_wrong_samples(pos_wrong, neg_wrong):
    all_models = set(pos_wrong.keys()) | set(neg_wrong.keys())
    print("=== 样本结果统计 ===")
    for model in sorted(all_models):
        wrong_pos_set = pos_wrong.get(model, set())
        wrong_neg_set = neg_wrong.get(model, set())
        print(f"模型 {model}:")
        print(f"  错误正样本 (FN): {len(wrong_pos_set)}, {wrong_pos_set}")
        print(f"  错误负样本 (FP): {len(wrong_neg_set)}, {wrong_neg_set}")


def extract_analysis_time_from_csv(csv_file):
    """
    从 CSV 文件中提取总分析时间
    时间通常在最后一行，格式为: "Total analysis time: X.XX seconds (...)"
    返回 (时间秒数, 是否成功提取)
    """
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                return 0, False

            # 查找最后一行包含 "Total analysis time" 的行
            for line in reversed(lines):
                if "Total analysis time" in line:
                    # 使用正则表达式提取时间数值
                    match = re.search(r'(\d+\.\d+)\s+seconds', line)
                    if match:
                        return float(match.group(1)), True
            return 0, False
    except Exception as e:
        print(f"[Warning] Failed to extract time from {csv_file}: {e}")
        return 0, False


def summarize_analysis_time(results_dir="../data/test_data/test_results_2026"):
    """
    汇总目录中所有 CSV 文件的分析时间，按模型分组
    """
    print(f"\n\n{'='*80}")
    print("ANALYSIS TIME SUMMARY BY MODEL")
    print(f"{'='*80}\n")

    model_times = defaultdict(list)  # {model_name: [(data_type, cot_type, time), ...]}
    total_by_model = defaultdict(float)  # {model_name: total_time}

    # 遍历目录中的所有 CSV 文件
    if not os.path.exists(results_dir):
        print(f"[Warning] Results directory not found: {results_dir}")
        return

    for filename in os.listdir(results_dir):
        # 匹配 mc_COT0_model_result.csv 或 sc_COT0_model_result.csv 格式
        # 或新格式 mc_COT0_model_result_missing.csv
        if not filename.endswith('.csv'):
            continue

        if '_result' not in filename:
            continue

        # 尝试提取信息
        # 文件格式: {data_type}_{cot_type}_{model_name}_result[_missing].csv
        # 例如: mc_COT0_DeepSeek-V3_result.csv
        base_name = filename.replace('_result.csv', '').replace('_result_missing.csv', '')
        parts = base_name.split('_')

        if len(parts) < 3:
            continue

        data_type = parts[0]  # mc 或 sc
        cot_type = parts[1]   # COT0, COT1, COT2, COT3

        # 模型名称是中间的部分（可能包含多个下划线或破折号）
        # 例如: qwen3-coder-plus-2025-07-22
        model_name = '_'.join(parts[2:])

        # 提取时间
        csv_file = os.path.join(results_dir, filename)
        time_seconds, success = extract_analysis_time_from_csv(csv_file)

        if success and time_seconds > 0:
            model_times[model_name].append((data_type, cot_type, time_seconds))
            total_by_model[model_name] += time_seconds

    # 显示结果
    if not model_times:
        print("[Info] No analysis time data found in CSV files")
        return

    print("{:<30s} {:>12s} {:>15s}".format("Model", "Total Time", "Files"))
    print("-" * 70)

    for model in sorted(model_times.keys()):
        total_time = total_by_model[model]
        num_files = len(model_times[model])
        minutes = total_time / 60.0

        print("{:<30s} {:>8.2f}s ({:>6.2f}m) {:>8d}".format(
            model, total_time, minutes, num_files
        ))

    # 显示详细信息
    print(f"\n{'─'*70}")
    print("Detailed Analysis Time by Model and COT Type:")
    print(f"{'─'*70}\n")

    for model in sorted(model_times.keys()):
        print(f"Model: {model}")
        print("  {:<8s} {:<8s} {:>12s}".format("DataType", "COTType", "Time"))
        print("  " + "-" * 35)

        # 按数据类型和 COT 类型排序
        entries = sorted(model_times[model], key=lambda x: (x[0], x[1]))
        for data_type, cot_type, time_seconds in entries:
            print("  {:<8s} {:<8s} {:>8.2f}s".format(data_type, cot_type, time_seconds))

        print(f"  Total: {total_by_model[model]:.2f}s ({total_by_model[model]/60:.2f}m)\n")

    # 总体统计
    print(f"{'─'*70}")
    print("Overall Statistics:")
    print(f"{'─'*70}")
    total_all = sum(total_by_model.values())
    print(f"Total models: {len(model_times)}")
    print(f"Total time: {total_all:.2f}s ({total_all/60:.2f}m)")
    print(f"Average time per model: {total_all/len(model_times):.2f}s")
    

def analyze_critical_variables():
    """
    第一部分：关键变量（Critical Variable）分析
    从 LLM 输出中提取和评估关键变量的识别准确性
    """
    print("\n" + "="*80)
    print("PART 1: CRITICAL VARIABLE ANALYSIS")
    print("="*80 + "\n")

    base_dir = "../data/test_data/"
    base_results_dir = "../data/test_data/test_results_2026"
    data_types = ['mc', 'sc']
    prompt_types = ['COT0_', 'COT1_', 'COT2_', 'COT3_', 'Few-Shots_', 'Few-Shots1_']

    # 从注释的代码中恢复模型列表（实际运行时可配置）
    model_list = ['llama-3.3-70b', 'gemini-2.5-pro']#, 'qwen3-coder-480b-a35b-instruct', 'llama-3.3-70b', 'DeepSeek-V3']  # 'DeepSeek-V3', 'qwen3-coder-plus-2025-07-22',

    for dt in data_types:
        print(f"\n{'─'*70}")
        print(f"Data Type: {dt.upper()}")
        print(f"{'─'*70}\n")

        # 尝试获取 critical variables 映射
        cv_file = base_dir + dt + "_critical_variables.list"
        if not os.path.exists(cv_file):
            print(f"[Warning] CV file not found: {cv_file}")
            continue

        cv_map = get_cv_map(cv_file)

        for pt in prompt_types:
            cot_type = pt.strip('_')  # 'COT0', 'COT1', 'COT2', 'COT3'
            print(f"\n  [{cot_type}] Critical Variable Results:")
            print(f"  {'-'*60}")

            for model in model_list:
                # 输入目录可能在原始位置或test_results_2026目录下
                results_dir_1 = os.path.join(base_results_dir, f"{dt}/{pt}{model}")
                results_dir_2 = os.path.join(base_dir, f"{dt}/{pt}{model}")

                results_dir = None
                if os.path.isdir(results_dir_1):
                    results_dir = results_dir_1
                elif os.path.isdir(results_dir_2):
                    results_dir = results_dir_2

                if results_dir is None:
                    print(f"    [Skip] Directory not found for model: {model}")
                    continue

                # 生成输出文件名: COT0_DeepSeek-V3_mc_cv_results.csv
                output_filename = f"{cot_type}_{model}_{dt}_cv_results.csv"
                output_file_path = os.path.join(base_results_dir, output_filename)

                print(f"    Model: {model}")
                print(f"    Output: {output_filename}")
                try:
                    extract_cv_from_llm_results(cv_map, results_dir, dt, output_file_path)
                    print(f"    ✓ Results saved to {output_filename}")

                    # 检查文件完整性（文件编号 1-147）
                    missing_nums = check_missing_files(results_dir, 1, num_samples)
                    if missing_nums:
                        print(f"    [Info] Missing sample files: {len(missing_nums)} out of {num_samples}")
                        print(f"           Missing IDs: {sorted(missing_nums)[:20]}{'...' if len(missing_nums) > 20 else ''}")
                        # 将缺失信息追加到输出文件
                        with open(output_file_path, 'a', encoding='utf-8') as f:
                            f.write(f"\n# Missing file IDs: {sorted(missing_nums)}\n")
                    else:
                        print(f"    [Info] All {num_samples} sample files present")
                except Exception as e:
                    print(f"    [Error] {e}")
                    import traceback
                    traceback.print_exc()


def analyze_model_results(selected_models=None):
    """
    第二部分：模型性能（Model Results）分析
    基于从 test_results_2026 目录的 CSV 结果文件分析精度、召回率等指标

    参数:
        selected_models (list): 要分析的模型列表。如果为 None，则分析所有模型
    """
    print("\n" + "="*80)
    print("PART 2: MODEL PERFORMANCE ANALYSIS")
    if selected_models:
        print(f"Selected Models: {', '.join(selected_models)}")
    print("="*80 + "\n")

    base_results_dir = "../data/test_data/test_results_2026"

    # 四种 COT 类型的分析
    cot_types = {
        'COT0': 'COT0',
        'COT1': 'COT1',
        'COT2': 'COT2',
        'COT3': 'COT3',
        'Few-Shots': 'Few-Shots',
        'Few-Shots1': 'Few-Shots1'
    }

    # 存储所有分析结果
    all_results = {}

    for cot_name, cot_label in cot_types.items():
        print(f"\n{'═'*70}")
        print(f"Analysis for {cot_label} Prompt Type")
        print(f"{'═'*70}\n")

        # 使用统一的结果目录（test_results_2026）
        # 这个目录包含所有 CSV 结果文件
        cot_results_dir = base_results_dir
        cot_results_cv_dir = base_results_dir

        # 检查目录是否存在
        if not os.path.isdir(cot_results_dir):
            print(f"[Skip] Results directory not found: {cot_results_dir}")
            continue

        # 尝试加载结果
        try:
            # 现在所有结果文件都在同一目录中
            # parse_files 按 COT 类型过滤文件，并按模型过滤（如果指定了）
            model_results, model_correct_samples, model_pos_correct, model_neg_correct, \
            model_wrong_samples, model_pos_wrong, model_neg_wrong = parse_files(
                cot_results_dir, cot_results_cv_dir, cot_label, selected_models
            )

            all_results[cot_name] = {
                'model_results': model_results,
                'correct_samples': model_correct_samples,
                'pos_correct': model_pos_correct,
                'neg_correct': model_neg_correct,
                'wrong_samples': model_wrong_samples,
                'pos_wrong': model_pos_wrong,
                'neg_wrong': model_neg_wrong
            }

            # 显示性能指标
            print(f"Per-Model Metrics for {cot_label}:")
            print("-" * 70)
            display(model_results)

            # 显示故障分析
            print(f"\nFailure Analysis for {cot_label}:")
            print("-" * 70)
            display_model_wrong_samples(model_pos_wrong, model_neg_wrong)

        except Exception as e:
            print(f"[Error] Failed to analyze {cot_label}: {e}")
            import traceback
            traceback.print_exc()

    # 补充：按照每个模型，展示 COT0-COT3 的性能对比
    print(f"\n\n{'='*80}")
    print("MODEL PERFORMANCE COMPARISON (COT0-COT3)")
    print(f"{'='*80}\n")

    # 收集所有模型名称
    all_models = set()
    for cot_data in all_results.values():
        all_models.update(cot_data['model_results'].keys())

    # 按模型显示 COT0-COT3 的对比
    for model in sorted(all_models):
        print(f"\n{'─'*70}")
        print(f"Model: {model}")
        print(f"{'─'*70}")
        print("{:<10s} {:>12s} {:>12s} {:>12s} {:>10s}".format(
            "COT Type", "Precision", "Recall", "F1", "Accuracy"
        ))
        print("-" * 70)

        for cot_name in ['COT0', 'COT1', 'COT2', 'COT3', 'Few-Shots', 'Few-Shots1']:
            if cot_name in all_results:
                model_results = all_results[cot_name]['model_results']
                if model in model_results:
                    y_true = model_results[model]["y_true"]
                    y_pred = model_results[model]["y_pred"]
                    if y_true:
                        accuracy, precision, recall, f1, _, _ = compute_metrics(y_true, y_pred)
                        print("{:<10s} {:>12.4f} {:>12.4f} {:>12.4f} {:>10.4f}".format(
                            cot_name, precision, recall, f1, accuracy
                        ))
                    else:
                        print("{:<10s} {:>12s} {:>12s} {:>12s} {:>10s}".format(
                            cot_name, "N/A", "N/A", "N/A", "N/A"
                        ))
                else:
                    print("{:<10s} {:>12s} {:>12s} {:>12s} {:>10s}".format(
                        cot_name, "N/A", "N/A", "N/A", "N/A"
                    ))
            else:
                print("{:<10s} {:>12s} {:>12s} {:>12s} {:>10s}".format(
                    cot_name, "N/A", "N/A", "N/A", "N/A"
                ))

    return all_results


def analyze_performance_gaps(all_results):
    """
    分析为什么某些提示类型的性能不如其他类型
    特别是：
    1. Few-Shots 的 precision/recall 为什么不如 COT0
    2. Few-Shots1 的 precision/recall 为什么不如 COT3
    """
    print(f"\n\n{'='*80}")
    print("PERFORMANCE GAP ANALYSIS")
    print(f"{'='*80}\n")

    # 比较对象对
    comparisons = [
        ('Few-Shots', 'COT0', '为什么Few-Shots的性能不如COT0'),
        ('Few-Shots1', 'COT3', '为什么Few-Shots1的性能不如COT3'),
    ]

    for prompt_type_1, prompt_type_2, description in comparisons:
        print(f"\n{'─'*70}")
        print(f"{description}")
        print(f"{'─'*70}\n")

        if prompt_type_1 not in all_results or prompt_type_2 not in all_results:
            print(f"[Skip] 缺少必要的分析数据\n")
            continue

        data_1 = all_results[prompt_type_1]
        data_2 = all_results[prompt_type_2]

        # 获取所有模型
        models = set(data_1['model_results'].keys()) | set(data_2['model_results'].keys())

        for model in sorted(models):
            print(f"\n  模型: {model}")
            print(f"  {'-'*60}")

            if model not in data_1['model_results'] or model not in data_2['model_results']:
                print(f"  [Skip] 模型数据不完整\n")
                continue

            results_1 = data_1['model_results'][model]
            results_2 = data_2['model_results'][model]

            y_true_1 = results_1['y_true']
            y_pred_1 = results_1['y_pred']
            y_true_2 = results_2['y_true']
            y_pred_2 = results_2['y_pred']

            # 计算性能指标
            _, prec_1, recall_1, f1_1, _, _ = compute_metrics(y_true_1, y_pred_1)
            _, prec_2, recall_2, f1_2, _, _ = compute_metrics(y_true_2, y_pred_2)

            # 计算性能差距
            prec_gap = prec_2 - prec_1
            recall_gap = recall_2 - recall_1
            f1_gap = f1_2 - f1_1

            print(f"  {prompt_type_1} 性能:")
            print(f"    Precision: {prec_1:.4f}, Recall: {recall_1:.4f}, F1: {f1_1:.4f}")
            print(f"  {prompt_type_2} 性能:")
            print(f"    Precision: {prec_2:.4f}, Recall: {recall_2:.4f}, F1: {f1_2:.4f}")
            print(f"  性能差距:")
            print(f"    Precision差异: {prec_gap:+.4f} ({prec_gap*100:+.2f}%)")
            print(f"    Recall差异:    {recall_gap:+.4f} ({recall_gap*100:+.2f}%)")
            print(f"    F1差异:        {f1_gap:+.4f}\n")

            # 分析错误样本
            pos_wrong_1 = data_1['pos_wrong'].get(model, set())  # FN: 应该是1但预测为0
            neg_wrong_1 = data_1['neg_wrong'].get(model, set())  # FP: 应该是0但预测为1
            pos_wrong_2 = data_2['pos_wrong'].get(model, set())
            neg_wrong_2 = data_2['neg_wrong'].get(model, set())

            # 找出在prompt_type_1中出错但在prompt_type_2中正确的样本
            fn_improved = pos_wrong_1 - pos_wrong_2  # FN在type_2中被改正
            fp_improved = neg_wrong_1 - neg_wrong_2  # FP在type_2中被改正
            fn_worsened = pos_wrong_2 - pos_wrong_1  # FN在type_2中恶化
            fp_worsened = neg_wrong_2 - neg_wrong_1  # FP在type_2中恶化

            print(f"  错误样本对比 ({prompt_type_1} vs {prompt_type_2}):")
            print(f"    {prompt_type_1} 的 False Negatives (应检查未检查): {len(pos_wrong_1)}")
            print(f"    {prompt_type_2} 的 False Negatives: {len(pos_wrong_2)}")
            print(f"    {prompt_type_1} 的 False Positives (不应检查但检查): {len(neg_wrong_1)}")
            print(f"    {prompt_type_2} 的 False Positives: {len(neg_wrong_2)}")

            if fn_improved:
                print(f"\n    -> {prompt_type_2} 相比 {prompt_type_1} 改正的 False Negatives: {len(fn_improved)}")
                print(f"       样本ID: {sorted(list(fn_improved))[:10]}{'...' if len(fn_improved) > 10 else ''}")

            if fp_improved:
                print(f"\n    -> {prompt_type_2} 相比 {prompt_type_1} 改正的 False Positives: {len(fp_improved)}")
                print(f"       样本ID: {sorted(list(fp_improved))[:10]}{'...' if len(fp_improved) > 10 else ''}")

            if fn_worsened:
                print(f"\n    -> {prompt_type_2} 相比 {prompt_type_1} 恶化的 False Negatives: {len(fn_worsened)}")
                print(f"       样本ID: {sorted(list(fn_worsened))[:10]}{'...' if len(fn_worsened) > 10 else ''}")

            if fp_worsened:
                print(f"\n    -> {prompt_type_2} 相比 {prompt_type_1} 恶化的 False Positives: {len(fp_worsened)}")
                print(f"       样本ID: {sorted(list(fp_worsened))[:10]}{'...' if len(fp_worsened) > 10 else ''}")

            # 根据结果总结
            # 注意：gap = prompt_type_2 - prompt_type_1
            # 所以 gap > 0 表示 prompt_type_2 更好，gap < 0 表示 prompt_type_1 更好
            print(f"\n  分析总结:")
            if prec_gap > 0 and recall_gap > 0:
                print(f"    {prompt_type_1} 的性能明显低于 {prompt_type_2}:")
                print(f"    - Precision 低 {prec_gap*100:.2f}%")
                print(f"    - Recall 低 {recall_gap*100:.2f}%")
                print(f"    主要问题: False {'Positives' if len(fp_worsened) > len(fn_worsened) else 'Negatives'} 过多")
            elif prec_gap > 0:
                print(f"    {prompt_type_1} 的 Precision 低于 {prompt_type_2}（低 {prec_gap*100:.2f}%）")
                print(f"    原因: 过度预测正例（False Positives）过多，导致精度下降")
            elif recall_gap > 0:
                print(f"    {prompt_type_1} 的 Recall 低于 {prompt_type_2}（低 {recall_gap*100:.2f}%）")
                print(f"    原因: 漏检（False Negatives）过多，导致召回率下降")
            elif prec_gap < 0 or recall_gap < 0:
                print(f"    {prompt_type_1} 的性能优于 {prompt_type_2}:")
                if prec_gap < 0:
                    print(f"    - Precision 高 {abs(prec_gap)*100:.2f}%")
                if recall_gap < 0:
                    print(f"    - Recall 高 {abs(recall_gap)*100:.2f}%")
            else:
                print(f"    {prompt_type_1} 和 {prompt_type_2} 的性能接近")

            print()


if __name__ == "__main__":
    import sys

    # 允许通过命令行参数选择分析部分和模型
    # python script.py cv  - 只分析 Critical Variables
    # python script.py model - 只分析 Model Results（所有模型）
    # python script.py model -m Model1 Model2 - 分析指定的模型
    # python script.py all - 分析两部分（默认）
    # python script.py all -m Model1 - 分析两部分，但 model 部分只分析指定模型

    mode = "all"
    selected_models = None

    # 解析命令行参数
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        if arg in ["cv", "model", "all"]:
            mode = arg
            i += 1
        elif arg in ["-m", "--model"]:
            # 收集后续的模型名称
            selected_models = []
            i += 1
            while i < len(sys.argv) and not sys.argv[i].startswith('-'):
                selected_models.append(sys.argv[i])
                i += 1
        else:
            i += 1

    print(f"[Config] Mode: {mode}")
    if selected_models:
        print(f"[Config] Selected models: {', '.join(selected_models)}")
    print()

    if mode in ["cv", "all"]:
        try:
            analyze_critical_variables()
        except Exception as e:
            print(f"[Error] Critical Variable Analysis failed: {e}")
            import traceback
            traceback.print_exc()

    if mode in ["model", "all"]:
        try:
            all_results = analyze_model_results(selected_models)
            print(f"\n{'═'*70}")
            print("Analysis Complete - Results Summary by COT Type:")
            print(f"{'═'*70}")
            for cot_type in all_results.keys():
                print(f"✓ {cot_type}: Analysis completed")

            # 分析性能差距
            analyze_performance_gaps(all_results)

            # 汇总分析时间
            summarize_analysis_time("../data/test_data/test_results_2026")
        except Exception as e:
            print(f"[Error] Model Results Analysis failed: {e}")
            import traceback
            traceback.print_exc()