import os
from pathlib import Path
import json
from tqdm import tqdm
import sys
import json
import myutil
import re
import os
from collections import Counter
import pandas as pd

src_code_info = {}

def classify_content_type(content):
    code = " ".join(content)
    if code:
        code = code.strip()
        pattern_returning = re.compile(
            r'([A-Za-z_][\w\s\*]+)\s+(\w+)\s*=\s*([A-Za-z_]\w*)\s*\((.*?)\);',
            re.DOTALL
        )
        if pattern_returning.search(code):
            return 'Returning Function Call'
        
        pattern_void = re.compile(
            r'([A-Za-z_]\w*)\s*\((.*?)\);',
            re.DOTALL
        )
        if pattern_void.search(code):
            return 'Void Function Call'
        return 'Other'

# Add line numbers to the source context lines
def get_src_context_with_linenum(src_context, start_line):
    updated_context = []
    for idx, ctx_line in enumerate(src_context):
        # print(f"{idx:>4}: {ctx_line.rstrip()}")
        ctx_line = ctx_line.strip() + "//##" + str(start_line + idx )
        updated_context.append(ctx_line)
    # print("old context: ", src_context)
    # print("updated context: ", updated_context)
    return updated_context

# Match the file in the given subsystem and return the matched lines
def match_file(src_root, subsystem, file_name, lineno):
    # print(subsystem, file_name, lineno)
    matched = []
    matched_src_line = []
    full_paths = []
    for dirpath, _, filenames in os.walk(src_root):
        if file_name in filenames and file_name.endswith('.c'):
            full_path = os.path.join(dirpath, file_name)
            if subsystem in os.path.relpath(full_path, src_root):
                # print(full_path, lineno)
                with open(full_path, 'r') as f:
                    content = f.readlines()
                    # print(full_path, lineno, len(content))
                    if len(content) < lineno:
                        break
                    # flag = False
                    for i, line in enumerate(content):
                        if i + 1 == lineno:
                            matched.append(full_path)
                            matched_src_line.append(line.strip())
                            src_code_info[full_path + f"_{lineno}"] = line.strip()
                            break
    return matched, matched_src_line

# Get context lines before the specified line number in the file
def get_line_src_before_file(src_root, file_name, lineno, count):
    if not os.path.exists(file_name):
        print(f"[Warning] File not found: {file_name}")
        return None
    # for dirpath, _, filenames in os.walk(src_root):
    #     if file_name in filenames and file_name.endswith('.c'):
    #         full_path = os.path.join(dirpath, file_name)
    #         if file_name in os.path.relpath(full_path, src_root):
    #             # print(full_path, lineno)
    #             full_path = os.path.join(dirpath, file_name)
    with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.readlines()
        # print(full_path, lineno, len(content))
        if len(content) < lineno:
            return None
        flag = False
        start_line = max(0, lineno - count-1)
        context_lines = content[start_line:lineno-1 ]
        start_line_=start_line+1
        context_lines = get_src_context_with_linenum(context_lines, start_line_)

        # print(f"--- Context before line {lineno} in {file_name} ---")
        # for idx, ctx_line in enumerate(context_lines, start=start_line + 1):
        #     print(f"{idx:>4}: {ctx_line.rstrip()}")
        target_line = content[lineno - 1]
        # print(f"{lineno:>4}: {target_line.rstrip()}")
        # if len(target_line.strip()) == 0 or not any(sym in target_line for sym in [';', '(', '=', '{']):
        #     flag = True
        # if flag:
        #     continue
        # else:
        return context_lines
    # return None

# Get context lines after the specified line number in the file
def get_line_src_after_file(src_root, file_name, lineno, count):
    if not os.path.exists(file_name):
        print(f"[Warning] File not found: {file_name}")
        return None
    # for dirpath, _, filenames in os.walk(src_root):
    #     if file_name in filenames and file_name.endswith('.c'):
    #         full_path = os.path.join(dirpath, file_name)
    #         if file_name in os.path.relpath(full_path, src_root):
    #             # print(full_path, lineno)
    #             full_path = os.path.join(dirpath, file_name)
    with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.readlines()
        # print(full_path, lineno, len(content))
        if len(content) < lineno:
            return None
        end_line = min(len(content), lineno + count)

        # flag = False
        start_line = max(0, lineno+1)
        context_lines = content[lineno :end_line]
        context_lines = get_src_context_with_linenum(context_lines, start_line)
        # print(f"--- Context before line {lineno} in {file_name} ---")
        # for idx, ctx_line in enumerate(context_lines, start=start_line + 1):
        #     print(f"{idx:>4}: {ctx_line.rstrip()}")
        target_line = content[lineno - 1]
        # print(f"{lineno:>4}: {target_line.rstrip()}")
        # if len(target_line.strip()) == 0 or not any(sym in target_line for sym in [';', '(', '=', '{']):
        #     flag = True
        # if flag:
        #     continue
        # else:
        return context_lines

        # print(f"{lineno:>4}: {target_line.rstrip()}")
        # return target_line.strip(), context_lines
    # return None

# Get context lines before the specified line number in the file
def get_line_src_before_after_file(fsrc_root, file_name, lineno, count):
                if not os.path.exists(file_name):
                    print(f"[Warning] File not found: {file_name}")
                    return None, None
                with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.readlines()
                    # print(full_path, lineno, len(content))
                    if lineno < 1 or lineno > len(content):
                        return None, None  # lineno out of range
                    # flag = False
                    start_line = max(0, lineno - (count + 1))
                    end_line = min(len(content), lineno+ count)
                    context_lines = content[start_line:end_line]
                    context_lines = get_src_context_with_linenum(context_lines, start_line+1)
                    # print(f"--- Context before line {lineno} in {full_path} ---")
                    # for idx, ctx_line in enumerate(context_lines, start=start_line + 1):
                    #     print(f"{idx:>4}: {ctx_line.rstrip()}")
                    target_line = content[lineno - 1]
                    # print(f"{lineno:>4}: {target_line.rstrip()}")
                    # if len(target_line.strip()) == 0 or not any(sym in target_line for sym in [';', '(', '=', '{']):
                    #     flag = True
                    # if flag:
                    #     continue
                    # else:
                    return target_line.strip(), context_lines
                return None, None

# Get context lines before and after the specified line number in the file
def get_line_src_before_after_path(src_root, src_path, lineno, count):
    full_path = os.path.join(src_root, src_path)
    print("full_path: ", full_path)
    if not os.path.exists(full_path):
        print(f"[Warning] File not found: {full_path}")
        return None, None
    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.readlines()
        if lineno < 1 or lineno > len(content):
            return None, None  # lineno out of range
        start_line = max(0, lineno - 1 - count)
        end_line = min(len(content), lineno + count)  # +1 because slicing excludes the end
        context_lines = content[start_line:end_line]
        context_lines = get_src_context_with_linenum(context_lines, start_line+1)
        target_line = content[lineno - 1]
        return target_line.strip(), context_lines
    return None, None

# Get context lines after the specified line number in the file
def get_line_src_uncheck_after(src_root, src_path, lineno, count):
    full_path = os.path.join(src_root, src_path)
    if not os.path.exists(full_path):
        print(f"[Warning] File not found: {full_path}")
        return None, None
    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.readlines()
                    # print(full_path, lineno, len(content))
        if len(content) < lineno:
            return None
        end_line = min(len(content), lineno - 1 + count)
        context_lines = content[lineno - 1:end_line]
        context_lines = get_src_context_with_linenum(context_lines, lineno - 1)
        target_line = content[lineno - 1]
        # print(f"--- Context after line {lineno} in {full_path} ---")
        # for idx, ctx_line in enumerate(context_lines, start=lineno):
             # print(f"{idx:>4}: {ctx_line.rstrip()}")
        return context_lines
    return None

# Get context lines before the specified line number in the file without checks
def get_line_src_uncheck_before(src_root, src_path, lineno, count):
    full_path = os.path.join(src_root, src_path)
    # print(full_path)
    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.readlines()
                    # print(full_path, lineno, len(content))
        if len(content) < lineno:
            return None
        start_line = max(0, lineno - (count + 1))
        context_lines = content[start_line:lineno - 1]
        context_lines = get_src_context_with_linenum(context_lines, start_line)
        # print(f"--- Context before line {lineno} in {full_path} ---")
        # for idx, ctx_line in enumerate(context_lines, start=start_line + 1):
        #     print(f"{idx:>4}: {ctx_line.rstrip()}")
        # target_line = content[lineno - 1]
        # print(f"{lineno:>4}: {target_line.rstrip()}")
        # if len(target_line.strip()) == 0 or not any(sym in target_line for sym in [';', '(', '=', '{']):
        return context_lines
    return None

# Match the file in the given subsystem and return the matched lines before and after the specified line number
def match_file_before_after(src_root, subsystem, file_name, lineno, count):
    matched = []
    matched_context_lines = []
    for dirpath, _, filenames in os.walk(src_root):
        if file_name in filenames and file_name.endswith('.c'):
            full_path = os.path.join(dirpath, file_name)
            if subsystem in os.path.relpath(full_path, src_root):
                # target_src, src_contexts = get_line_src_before_after_file(full_path, int(lineno), count)
                target_src, src_contexts = get_line_src_before_after_file(src_root, full_path, int(lineno), count)
                if target_src is not None:
                    print(f"{file_name};{lineno};{target_src};{src_contexts}")
                    matched.append(full_path)
                    matched_context_lines.append(target_src)
                    matched_context_lines.append(src_contexts)
                    continue
    return matched, matched_context_lines[0], matched_context_lines[1]

# normalize paths to consistent format
def normalize_path(path):
    """Normalize paths to consistent format"""
    path = str(Path(path).resolve())  # Convert to absolute path
    # Standardize path separators and remove redundant parts
    path = os.path.normpath(path)
    # Extract path relative to linux-4.20-rc5
    # print("Original path:", path)
    if 'linux-4.20-rc5' in path:
        path = path.split('linux-4.20-rc5')[-1].lstrip('/\\')
        # print("Normalized path:", path)
        path = path.replace('\\', '/')
    return path

# Match paper results with crix results
def match_paper_report_results_classify_label(bug_path, paper_match, bug_report_path, clssify_flag):
    labels = []
    matches = []
    matches_src_set = set()
    src_set = set()
    count = 0
    with open(paper_match, 'r') as src_file, open(bug_report_path, 'r') as report_file:
        # Read and pre-process source lines
        src_lines = []
        for line in src_file:
            line = line.strip('\r\n')
            parts = [p.strip() for p in line.split(' ;; ')]
            if len(parts) >= 5:
                src_path = normalize_path(parts[1])
                src_linenum = parts[3]
                src_lines.append((src_path.strip(), src_linenum.strip(), line.strip()))
                src_set.add(line.strip())

        # print(src_lines[:1])  # Print first 5 lines for debugging
        # Process bug reports
        report_lines = report_file.readlines()
        print(report_lines[:1])
        seq = 0
        for report_line in report_lines:
            seq += 1
            report_line = report_line.strip('\r\n')
            # report_line = report_line.strip()
            parts = [p.strip() for p in report_line.split(' ;; ')]
            if len(parts) >= 5:
                if clssify_flag == 0:
                    ### bug list no classify
                    report_path = normalize_path(parts[1])
                    report_linenum = parts[3]
                else :
                    ### bug list classify
                    report_path = normalize_path(parts[0])
                    report_linenum = parts[1]
                
            flag = False
            for src_path, src_linenum, src_line in src_lines:
                if src_path == report_path and src_linenum == report_linenum:
                        labels.append('1')
                        matches.append(report_line)
                        matches_src_set.add(src_line)
                        # print(parts[2], parts[4])
                        flag = True
                        count += 1
                        break
            if not flag:
                labels.append('0')

        diff = src_set - matches_src_set
        for d in diff:
            print(d)
        
        # Write matched results
        if labels:
            if clssify_flag == 0:
                with open(os.path.join(bug_path, 'paper_crix_matched_labels_no_classify_test.list'), 'w') as out_file_labels0:
                    out_file_labels0.write('\n'.join(labels))
                with open(os.path.join(bug_path, 'paper_crix_matched_10_no_classify_test.list'), 'w') as out_file_matches0:
                    out_file_matches0.write('\n'.join(matches))
            elif clssify_flag == 1:
                with open(os.path.join(bug_path, 'paper_crix_matched_labels_classify_test.list'), 'w') as out_file_labels:
                    out_file_labels.write('\n'.join(labels))
                with open(os.path.join(bug_path, 'paper_crix_matched_10_classify_test.list'), 'w') as out_file_matches:
                    out_file_matches.write('\n'.join(matches))
            else:
                with open(os.path.join(bug_path, 'paper_crix_matched_labels_classify_full_contexts_test.list'), 'w') as out_file_labels1:
                    out_file_labels1.write('\n'.join(labels))
                with open(os.path.join(bug_path, 'paper_crix_matched_10_classify_full_contexts_test.list'), 'w') as out_file_matches1:
                    out_file_matches1.write('\n'.join(matches))

        print(f"Total matches found: {count}")

# Get paper results and match kernel paths
def get_paper_results(input_dir, src_path):
    results = set()
    matched_file = open(os.path.join(input_dir, 'matched_before_after_use_10.list'), 'w', encoding="utf-8")
    not_found_file = open(os.path.join(input_dir, 'no_found_before_after_use_10.list'), 'w', encoding="utf-8")
    with open(os.path.join(input_dir, "bug-list-crix-kernel4.20-rc5.csv"), 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            if parts[2].strip() == 'Line#':
                continue

            subsystem = parts[0].strip()  # maybe drivers/net etc.
            file_name = parts[1].strip()  # maybe super.c
            lineno = parts[2].strip()  # maybe 1234
            # print('aaaa', subsystem, file_name, lineno)

            # matches, matched_src_line = match_file(src_path, subsystem, file_name, int(lineno))
            # source kernel code: 10 lines from buggy file line
            matches, matched_src_line, matched_src_context = match_file_before_after(src_path, subsystem, file_name, int(lineno), 10)
            print(matches, matched_src_line, matched_src_context)
            r = matches[0] + ":" + lineno
            if len(matches) == 1 and r not in results:
                results.add(r)
                results.add(f"{matches[0]}"+f":{lineno}")
                matched_file.write(f"{subsystem} ;; {matches[0]} ;; {file_name} ;; {lineno} ;; {matched_src_line} ;; {matched_src_context}\n")
                print(f"Matched: {file_name} => {matches[0]}")
            else:
                not_found_file.write(f"{file_name} under {subsystem}\n")
                print(f"Not found: {file_name}, {lineno} under {subsystem}")
    matched_file.close()
    not_found_file.close()

def process_checked_use_selected(checked_list_path, src_root, output_path):
    with open(checked_list_path, 'r') as infile, open(output_path, 'w', encoding='utf-8') as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            try:
                path, lineno_str = line.split(':')
                lineno = int(lineno_str)
                subsystem = path.split('/')[0]

                target_line, context_lines = get_line_src_before_after_path(src_root, path, lineno, 10)
                if context_lines is None:
                    print(f"[Skip] Cannot find context for {path}:{lineno}")
                    continue
                
                context_str = ''.join(context_lines).strip()
                file_name = os.path.basename(path)
                full_path = os.path.join(src_root, path).replace('\\', '/')

                outfile.write(f"{subsystem} ;; {full_path} ;; {file_name} ;; {lineno} ;; {target_line} ;; {context_str}\n")
            except Exception as e:
                print(f"[Error] Failed to process line: {line} -> {e}")

def get_checked_list(path):
    checked_uses = set()
    cnt = 0
    data = myutil.load_json_file('../data/crix-results/results-4.20-rc5/results-0.15/output_sc.json')
    with tqdm(total=len(data), desc="Processing items", ) as pbar:
        for key, val in data.items():
            for use_loc in val['use_locs']:
                print("use_loc:", use_loc)
                try:
                    use_loc_file, use_loc_no = myutil.split_weird_str2(use_loc)
                    print("use_loc_file:", use_loc_file, "use_loc_no:", use_loc_no)
                    if len(use_loc_file) == 0 or int(use_loc_no) <= 0:
                        print(f"Invalid use location format: {use_loc}", file=sys.stdout)
                        continue
                    # print(use_loc_file + ":" + use_loc_no)
                    # use_line = myutil.load_src_file_line(use_loc_file, use_loc_no)
                except ValueError as e:
                    # print(f"Error processing use location '{use_loc}': {e}", file=sys.stdout)
                    continue
                except Exception as e:
                    # print(f"Unexpected error processing use location '{use_loc}': {e}", file=sys.stdout)
                    continue
                # if use_line.strip() == '':
                #     print(f"Empty use line at {use_loc_file}:{use_loc_no}", file=sys.stdout)
                #     continue
                # if use_line.strip().startswith('//'):
                #     print(f"Commented use line at {use_loc_file}:{use_loc_no}", file=sys.stdout)
                #     continue
                # if use_line.strip().startswith('/*'):
                #     print(f"Multiline comment use line at {use_loc_file}:{use_loc_no}", file=sys.stdout)
                #     continue
                # if use_line.strip().startswith('#'):
                #     print(f"Preprocessor directive use line at {use_loc_file}:{use_loc_no}", file=sys.stdout)
                #     continue
                if len(checked_uses) < 400 and (use_loc_file, use_loc_no) not in checked_uses:
                    checked_uses.add((use_loc_file, use_loc_no))
                if len(checked_uses) >= 400:
                    break 
                cnt += 1

    checked_uses = list(checked_uses)
    print(f"Total checked uses: {len(checked_uses)}")
    with open(os.path.join('../data/crix-results/results-4.20-rc5/results-0.15/', path), 'w', encoding='utf-8') as file:
        for use_loc_file, use_loc_no in checked_uses:
            file.write(f"{use_loc_file}:{use_loc_no}\n")
            
            
def get_type_function_sc_or_mc(src_path,input_path,output_path):
    other_lines = []
    type_counts = {
        'Returning Function Call': 0,
        'Void Function Call': 0,
        'Array Access': 0,
        'Function Definition': 0,
        'Assignment Statement': 0,
        'Other': 0
    }
    with open(input_path, 'r', encoding='utf-8') as infile, open(output_path, 'w', encoding='utf-8') as matched_file:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            try:
                parts = line.split(' ;; ')
                subsystem = parts[0]
                file_path=parts[1]
                lineno=parts[3]
                lineno_content=parts[4]
            except (IndexError, ValueError):
                print("错误：输入格式不正确。应为 '{path/to/file.c, line_number}'。")
                return None
            function_type=classify_line_type(lineno_content)
            if function_type == 'Returning Function Call':
                context_lines=get_line_src_after_file(src_path, file_path, int(lineno), 10)
                matched_file.write(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; {context_lines} ;; {function_type}\n")
                type_counts['Returning Function Call'] += 1
            elif function_type == 'Void Function Call':
                context_lines = get_line_src_before_file(src_path, file_path, int(lineno), 10)
                matched_file.write(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; {context_lines} ;; {function_type}\n")
                type_counts['Void Function Call'] += 1
            elif function_type == 'Array Access':
                context_lines = get_line_src_before_file(src_path, file_path, int(lineno), 10)
                matched_file.write(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; {context_lines} ;; {function_type}\n")
                type_counts['Array Access'] += 1
            elif function_type == 'Function Definition':
                context_lines = get_line_src_before_file(src_path, file_path, int(lineno), 10)
                matched_file.write(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; {context_lines} ;; {function_type}\n")
                type_counts['Function Definition'] += 1
            elif function_type == 'Assignment Statement':
                context_lines = get_line_src_before_file(src_path, file_path, int(lineno), 10)
                matched_file.write(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; {context_lines} ;; {function_type}\n")
                type_counts['Assignment Statement'] += 1
            elif function_type == 'Other':
                # context_lines = get_line_src_before_after_file(src_path, file_path, lineno, 10)
                other_lines.append(f"{subsystem} ;; {file_path} ;; {lineno} ;; {lineno_content} ;; other\n")
                type_counts['Other'] += 1
    # Write matched lines to output file
        for line in other_lines:
            matched_file.write(line)
        matched_file.write(json.dumps(type_counts, ensure_ascii=False) + "\n")
    matched_file.close()
    
def is_incomplete_line(line):
    """Check whether the line is incomplete"""
    line = line.strip()
    open_paren = line.count('(')
    close_paren = line.count(')')
    quote_count = line.count('"') + line.count("'")
    semicolon = line.endswith(';')
    line_end_op = re.search(r'[\+\-\*/&|,]$', line)  # trailing operator or comma at end of line

    incomplete = False
    reason = None

    if open_paren != close_paren:
        incomplete = True
        reason = 'paren'
    elif quote_count % 2 != 0:
        incomplete = True
        reason = 'quote'
    elif not semicolon and line_end_op:
        incomplete = True
        reason = 'line_end_op'

    return incomplete, reason

import re

def get_complete_statement_dynamic(content, lineno, max_extend=50): 
    """
    Dynamically extend the statement based on the type of incompleteness, stopping as soon as a complete statement is found.
    content: list of file content lines
    lineno: target line number (1-based)
    """
    target_idx = lineno - 1
    statement = content[target_idx].strip()

    # Return directly for empty lines or comments
    if not statement or statement.startswith('//') or statement.startswith('/*') or statement.startswith('*'):
        return statement

    # === Helper functions ===
    def balanced_all(s):
        stack = []
        pairs = {')': '(', ']': '['}
        for c in s:
            if c in '([':
                stack.append(c)
            elif c in ')]':
                if not stack or stack[-1] != pairs[c]:
                    return False
                stack.pop()
        return len(stack) == 0

    def is_control_statement(s):
        return re.match(r'^\s*(if|while|for|switch|do|else)\b', s) is not None

    def is_macro_or_annotation(s):
        s = s.strip()
        return s.startswith('#') or s.startswith('//') or s.startswith('/*') or s.startswith('*')
        # return bool(re.match(r'^\s*(#|//|/\*|\*)', s))

    def is_complete(s):
        s_stripped = s.rstrip()
        if (s_stripped.endswith(';') or is_control_statement(s_stripped)):
            if balanced_all(s_stripped) and s_stripped.count('"') % 2 == 0 and s_stripped.count("'") % 2 == 0:
                return True
        return False

    def is_function_call_end(s):
        s = s.strip()
        if not s.endswith(';'):
            return False
        if not balanced_all(s):
            return False
        return bool(re.search(r'\b[a-zA-Z_]\w*\s*\([^)]*\)\s*;\s*$', s))

    def is_incomplete_assignment(s):
        s = s.strip()
        if s.startswith('//') or s.startswith('#'):
            return False
        if '=' in s and '==' not in s and '!=' not in s:
            if s.endswith(';'):
                return False
            if re.search(r'=\s*$', s):
                return True
            if not re.search(r'=\s*[^;]+;', s):
                return True
            # Check whether there is content after the assignment operator (avoid matching '=' inside function args)
            equals_pos = s.find('=')
            if equals_pos > 0:
                # Check whether what precedes the '=' is a valid identifier or member access
                before_equals = s[:equals_pos].strip()
                if (re.search(r'[a-zA-Z_]\w*$', before_equals) or 
                    re.search(r'[\]\)]\.?->?\s*\w*$', before_equals) or
                    re.search(r'\w+\s*$', before_equals)):
                    return True
        return False

    def is_standalone_statement(s):
        """Check whether this is a standalone statement (should not be merged with what precedes it)"""
        s = s.strip()
        # Complete statement ending with a semicolon
        if s.endswith(';'):
            return True
        # Control statement
        if is_control_statement(s):
            return True
        # Block start/end
        if s.endswith('{') or s.endswith('}'):
            return True
        # Complete function declaration or definition
        if re.match(r'^\s*\w+\s+\w+\s*\([^)]*\)\s*\{?\s*$', s):
            return True
        return False

    def looks_like_continuation(prev_line, current_stmt):
        """Check whether the previous line looks like a continuation of the current statement"""
        prev = prev_line.rstrip()
        curr_start = current_stmt.lstrip()

        # Previous line ends with an operator, likely an expression continuation
        if re.search(r'[+\-*/%&|\^=<>,([]\s*$', prev):
            return True
        # Previous line ends with a word character and current line starts with an operator, likely an expression continuation
        if re.search(r'\w\s*$', prev) and re.match(r'^\s*[+\-*/%&|\^=<>.,]', curr_start):
            return True
        # Previous line has an unclosed parenthesis
        if not balanced_all(prev):
            return True
        return False

    start_idx = target_idx
    end_idx = target_idx
    extend_count = 0

    # === Extend forward to include following lines ===
    while extend_count < max_extend and end_idx + 1 < len(content):
        if is_function_call_end(statement) or is_complete(statement):
            # return statement
            break
        
        next_line = content[end_idx + 1].strip()
        if not next_line or is_macro_or_annotation(next_line):
            end_idx += 1
            extend_count += 1
            continue

        if re.match(r'^\s*(if|for|while|switch|do|else)\b', next_line) or '{' in next_line:
            break
        if statement.strip().endswith(';'):
            break

        statement += ' ' + next_line
        end_idx += 1
        extend_count += 1

        if is_function_call_end(statement) or is_complete(statement):
            # return statement
            break
    
    # === Extend backward to include preceding lines (improved) ===
    while start_idx > 0:
        prev_line = content[start_idx - 1].rstrip()

        # Stop condition: empty line, comment, or standalone statement encountered
        if not prev_line or is_macro_or_annotation(prev_line):
            break

        if is_standalone_statement(prev_line):
            break

        # Check whether it looks like a continuation
        # if not looks_like_continuation(prev_line, statement):
        #     break

        # Previous line is an assignment without a trailing semicolon
        if is_incomplete_assignment(prev_line):
            statement = prev_line + ' ' + statement
            start_idx -= 1
            continue

        new_stmt = prev_line + ' ' + statement

        # Parentheses unbalanced, keep searching backward for the start
        if not balanced_all(new_stmt):
            statement = new_stmt
            start_idx -= 1
            continue

        # Check whether the merged result forms a complete statement
        if is_function_call_end(new_stmt) or is_complete(new_stmt):
            statement = new_stmt
            start_idx -= 1
            # Keep going backward, there may be more related lines
            continue

        # If balanced but incomplete after merging, check whether to continue
        if looks_like_continuation(prev_line, statement):
            statement = new_stmt
            start_idx -= 1
        else:
            break

    return statement.strip()


def classify_line_type(line):
    line = line.strip()
    if not line.startswith('return '):
        line = line.replace(' ', '')
    if not line:
        return 'Other'

    # -------------------------------
    # 1. Returning Function Call
    # a) return function call
    # if re.search(r'.*?return\s+[A-Za-z_]\w*\s*\(.*\)\s*;?', line, re.DOTALL):
    #     return 'Returning Function Call'
    if re.search(
        r'return\s+[A-Za-z_]\w*(?:->\w+|\.\w+)*\s*\([^)]*\)\s*;?',
        line
    ):
        return 'Other'

    # b) function call assigned to an lvalue (lvalue can be an array or struct member)
    # if re.search(r'([A-Za-z_]\w*(?:->\w+|\.\w+|\[[^\]]+\])*)\s*=\s*[A-Za-z_]\w*\s*\(.*\)\s*;?', line, re.DOTALL):
    # if re.search(r'([A-Za-z_]\w*(?:->\w+|\.\w+|\[[^\]]+\])*)\s*=\s*([A-Za-z_]\w*(?:->\w+|\.\w+)*\s*\(.*\))\s*;?', line, re.DOTALL):
    #     return 'Returning Function Call'
    pattern = re.compile(
        r'([A-Za-z_]\w*(?:->\w+|\.\w+|\[[^\]]+\])*)'   # left-hand side variable
        r'\s*=\s*'                                     # assignment operator
        r'(?:\([^\)]*\)\s*)*'                          # optional type cast
        r'[A-Za-z_]\w*(?:->\w+|\.\w+)*\s*\([^)]*\)'    # function call part
        r'(?:->\w+|\.\w+)*',                           # optional trailing member access
        re.DOTALL
    )
    if pattern.search(line):
        return 'Returning Function Call'

    # -------------------------------
    # 2. Void Function Call
    # if re.match(r'^[A-Za-z_]\w*\s*\(.*\)\s*;?$', line):
    if re.match(r'^(?!\s*(if|while|for|switch)\s*\()[A-Za-z_]\w*(?:->\w+|\.\w+|::\w+)*\s*\(.*\)\s*;?', line):
        return 'Void Function Call'

    # -------------------------------
    # 3. Array / Struct Access
    # Array Access only matches standalone array accesses, not inside function call parens or assignment lvalues
    def is_array_access_outside_func_call(s):
        # Remove the contents inside all function call parentheses
        def remove_func_args(s):
            stack = []
            to_remove = []
            for i, c in enumerate(s):
                if c == '(':
                    stack.append(i)
                elif c == ')' and stack:
                    start = stack.pop()
                    to_remove.append((start, i))
            s_list = list(s)
            for start, end in reversed(to_remove):
                for idx in range(start, end+1):
                    s_list[idx] = ' '
            return ''.join(s_list)

        s_clean = remove_func_args(s)
        # Remove the lvalue array assignment part
        s_clean = re.sub(r'^[A-Za-z_]\w*(?:->\w+|\.\w+|\[[^\]]+\])*\s*=\s*', '', s_clean)
        # Find the remaining [ ]
        return bool(re.search(r'\[[^\]]+\]', s_clean))

    if is_array_access_outside_func_call(line):
        return 'Array Access'

    # -------------------------------
    # 4. Function Definition
    if not line.lstrip().startswith('return') and \
        re.match(r'^\s*[A-Za-z_][\w\s\*]*\s+([A-Za-z_]\w*)\s*\(.*\)\s*\{?', line, re.DOTALL):
        return 'Function Definition'
    
    # -------------------------------
    # 5. Assignment Statement
    if re.search(r'([A-Za-z_]\w*(?:->\w+|\.\w+|\[[^\]]+\])*)\s*=\s*[^=;\n]*[^;]\s*$', line, re.DOTALL):
        return 'Assignment Statement'

    return 'Other'


def get_type_function_bug(src_path, input_path_bug, output_path_bug, output_path_bug_full, output_path_bug_line_type):
    
    # other_lines = []
    type_counts = {
        'Returning Function Call': 0,
        'Void Function Call': 0,
        'Array Access': 0,
        'Function Definition': 0,
        'Assignment Statement': 0,
        'Other': 0
    }

    empty_lines=[]
    with open(input_path_bug, 'r', encoding='utf-8') as infile, open(output_path_bug, 'w', encoding='utf-8') as matched_file, \
        open(output_path_bug_full, 'w', encoding='utf-8') as matched_file1, open(output_path_bug_line_type, 'w', encoding='utf-8') as matched_file2:
        for idx, line in enumerate(infile, start=1): 
            ## for debug
            # if idx != 2091:
            #     continue
            
            line = line.strip()
            if not line:
                continue
            line = line.strip("{}")
            try:
                _, file_path, _, lineno, _, _ = line.split(" ;; ")
            except ValueError:
                print(f"Line {idx} parsing failed: {line}")
                continue

            file_path = file_path.strip()
            lineno = int(lineno.strip())
            if not file_path:
                empty_lines.append(idx) 
                continue

            full_path = os.path.join(file_path)
            if not os.path.exists(full_path):
                print(f"File not found: {full_path}")
                continue

            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.readlines()
                if len(content) < lineno:
                    print(f"File {full_path} has only {len(content)} lines, cannot access line {lineno}")
                    continue

                # Dynamically retrieve the complete statement
                target_line = get_complete_statement_dynamic(content, lineno, max_extend=20)
                # print("lineno: ", lineno )
                # print("target_line: ", target_line)

                # Classify the type
                function_type = classify_line_type(target_line)
                matched_file2.write(f"{idx}\t{function_type}\n")
                
                ## full contexts
                _, context_lines_full = get_line_src_before_after_file(src_path, full_path, lineno, 10)
                matched_file1.write(f"{full_path} ;; {lineno} ;; {target_line} ;; {context_lines_full} ;; {function_type}\n")

                # Context retrieval and writing logic
                if function_type in ['Returning Function Call', 'Void Function Call', 'Array Access',
                                     'Function Definition', 'Assignment Statement', 'Other']:
                    if function_type == 'Returning Function Call':
                        context_lines = get_line_src_after_file(src_path, full_path, lineno, 10)
                    elif function_type == 'Void Function Call' or function_type == 'Array Access':
                        context_lines = get_line_src_before_file(src_path, full_path, lineno, 10)
                    else:
                        _, context_lines = get_line_src_before_after_file(src_path, full_path, lineno, 10)
                    
                    matched_file.write(f"{full_path} ;; {lineno} ;; {target_line} ;; {context_lines} ;; {function_type}\n")
                    type_counts[function_type] += 1

                # elif function_type == 'Other':
                #     _, context_lines = get_line_src_before_after_file(full_path, lineno, 10)
                #     function_type_ = classify_content_type(context_lines)
                #     if function_type_ != 'Other':
                #         matched_file.write(f"{full_path} ;; {lineno} ;; {target_line} ;; {context_lines} ;; {function_type_}\n")
                #         type_counts[function_type_] += 1
                #     else:
                #         other_lines.append(f"{full_path} ;; {lineno} ;; {target_line} ;; {context_lines} ;; {function_type_}\n")
                #         type_counts['Other'] += 1

        # Output lines of type Other
        # for line in other_lines:
        #     matched_file.write(line)

        # Output statistics
        print(json.dumps(type_counts, ensure_ascii=False) + "\n")

    
def process_argmt_json_like_file(input_path, src_root):
    
    for json_file in [ input_path + '/output_use.json', input_path + '/output_src_argmt.json', input_path + '/output_src_param.json', input_path + '/output_src_retval.json']:
    
    # os.makedirs(os.path.dirname(output_path), exist_ok=True)

        pattern = re.compile(r'^\s*"(?P<path>.+?)\s+\+(?P<lineno>\d+)\s*:\s*(?P<code>.*)"\s*,?\s*$')
        seen = set()

        with open(json_file, 'r', encoding='utf-8') as infile, \
            open(json_file+'.list', 'w', encoding='utf-8') as outfile:

            for raw_line in infile:
                raw_line = raw_line.strip()
                if not raw_line or raw_line in {'[', ']'}:
                    continue

                match = pattern.match(raw_line)
                if not match:
                    print(f'格式不匹配: {raw_line[:80]}...')
                    continue

                path = match.group('path').strip()
                lineno = int(match.group('lineno'))
                key = (path, lineno)

                if key in seen:
                    continue  # deduplicate
                seen.add(key)

                subsystem = path.split('/')[0]
                file_name = os.path.basename(path)
                full_path = os.path.join(src_root, path).replace('\\', '/')

                target_line, context_lines = get_line_src_before_after_file(src_root, full_path, lineno, 10)
                if context_lines is None:
                    print(f'无法读取上下文: {path}:{lineno}')
                    continue

                context_str = ''.join(context_lines).strip()
                outfile.write(f'{subsystem} ;; {full_path} ;; {file_name} ;; {lineno} ;; {target_line} ;; {context_str}\n')

        print(f'处理完成，输出路径: {json_file}')
        
        
        
def merge_list_files(input_path, output_file, sort=False, unique=True):

    total_lines = 0
    seen = set() if unique else None
    buffer = []

    for fp in [ input_path + '/output_use.json.list', input_path + '/output_src_argmt.json.list', input_path + '/output_src_param.json.list', input_path + '/output_src_retval.json.list']:
        with open(fp, 'r', encoding='utf-8') as f:
            total_lines += sum(1 for _ in f)

    with tqdm(total=total_lines, desc='Merging') as pbar:
        for fp in [ input_path + '/output_use.json.list', input_path + '/output_src_argmt.json.list', input_path + '/output_src_param.json.list', input_path + '/output_src_retval.json.list']:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    pbar.update(1)
                    if unique:
                        if line in seen:
                            continue
                        seen.add(line)
                    buffer.append(line)

    if sort and unique:
        buffer = sorted(buffer)

    with open(output_file, 'w', encoding='utf-8') as out:
        out.writelines(buffer)

    print(f'合并完成{output_file}  总行数：{len(buffer)}')
    
def compare_old_new_bug_list(bug_file_0, bug_file_1, bug_path):
    with open(bug_file_0, 'r') as file, open(bug_file_1, 'r') as file1: 
        contents = [line.strip() for line in file]
        contents1 = [line.strip() for line in file1] 
        # print("length of lines: ", len(contents))
        # print("length of lines1: ", len(contents1))
        lines = contents
        lines1 = contents1
        
        ## bug-list-0.15 old and new compare
        # lines = [' ;; '.join(line.strip().split(' ;; ')[1:3]).strip() for line in contents]
        # lines1 = [' ;; '.join(line.strip().split(' ;; ')[0:2]).strip() for line in contents1] 
        print("length of lines: ", len(lines))
        print("length of lines1: ", len(lines1))
        
        cmp_file = open(bug_path + '/bug1_compare_bug2_delete.list', 'w', encoding='utf-8')
        cmp_file1 = open(bug_path + '/bug2_compare_bug1_add.list', 'w', encoding='utf-8')
        
        # ## merge all data need to be analyzed with LLM
        # merge_file = open(bug_path + '/bug1_new_add_merge.list', 'w', encoding='utf-8')
        # merge_set = set()
        # for line in lines:
        #     newline = re.compile(r'^\s*\d+\s*;;\s*').sub('', line) 
        #     if newline not in merge_set:
        #         merge_set.add(newline)
        #         merge_file.write(newline + '\n')
        # for line1 in lines1:
        #     newline1 = re.compile(r'^\s*\d+\s*;;\s*').sub('', line1)
        #     if newline1 not in merge_set:
        #         merge_set.add(newline1)
        #         merge_file.write(newline1 + '\n')    
        # merge_file.close()
        
        seq = 0
        for line in lines:
            if line not in set(lines1):
                # print(seq, line) 
                cmp_file.write(str(seq) + ' ;; ' + contents[seq] + '\n')   
            seq += 1
        
        seq1 = 0
        for line1 in lines1:
            if line1 not in set(lines):
                # print(seq1, line1)
                cmp_file1.write(str(seq1) + ' ;; ' + contents1[seq1] + '\n')
            seq1 += 1
        
        cmp_file.close()
        cmp_file1.close()

def generate_new_bug_list_results(bug_file_0, bug_file_1, old_results_file, add_results_file, new_results_file):
    with open(bug_file_0, 'r', encoding='utf-8') as file:
        contents = [line.strip() for line in file]
    with open(bug_file_1, 'r', encoding='utf-8') as file1:
        contents1 = [line.strip() for line in file1] 
        
    lines = contents
    lines1 = contents1
    
    ## bug-list-0.15 old and new compare
    # lines = [' ;; '.join(line.strip().split(' ;; ')[1:3]).strip() for line in contents]
    # lines1 = [' ;; '.join(line.strip().split(' ;; ')[0:2]).strip() for line in contents1] 
    # print("length of lines: ", len(lines))
    # print("length of lines1: ", len(lines1))
    
    # common_lines = set(lines) & set(lines1)
        
    # ids_file1 = [i + 1 for i, line in enumerate(lines) if line in common_lines]
    # ids_file2 = [i + 1 for i, line in enumerate(lines1) if line in common_lines]
        
    # old_results = pd.read_csv(old_results_file)
    
    # old_common = old_results[old_results["Sample_ID"].isin(ids_file1)].copy()
    
    # mapping = []
    # for line in common_lines:
    #     id1 = lines.index(line) + 1
    #     id2 = lines1.index(line) + 1
    #     mapping.append((id1, id2))  
    # mapping_df = pd.DataFrame(mapping, columns=["id_file1", "id_file2"])
    
    # old_common_sorted = old_common.sort_values(by="Sample_ID").reset_index(drop=True)
    # mapping_df_sorted = mapping_df.sort_values(by="id_file1").reset_index(drop=True)
    
    # new_generated = old_common_sorted.copy()
    # new_generated["Sample_ID_File1"] = mapping_df_sorted["id_file1"].values
    # new_generated["Sample_ID"] = mapping_df_sorted["id_file2"].values
    
    # try:
    #     add_results = pd.read_csv(add_results_file)
    #     final_results = pd.concat([new_generated, add_results], ignore_index=True)
    # except FileNotFoundError:
    #     print("not found file")
    #     final_results = new_generated
    
    # if "Sample_ID" in final_results.columns:
    #     final_results = final_results.dropna(subset=["Sample_ID"])
    #     final_results["Sample_ID"] = final_results["Sample_ID"].astype(int)
    # if "Sample_ID_File1" in final_results.columns:
    #     final_results["Sample_ID_File1"] = final_results["Sample_ID_File1"].fillna(-1).astype(int)

    # path_col = final_results.columns[-1]

    # def replace_in_path(path, new_id_str):
    #     if not isinstance(path, str):
    #         return path
    #     # Match common form: __123_output
    #     m = re.search(r'__(\d+)_output', path)
    #     if m:
    #         return re.sub(r'__(\d+)(_output)', f'__{new_id_str}\\2', path, count=1)
    #     # Match: _123_output
    #     m = re.search(r'_(\d+)_output', path)
    #     if m:
    #         return re.sub(r'_(\d+)(_output)', f'_{new_id_str}\\2', path, count=1)
    #     # Otherwise match the last number
    #     m = re.search(r'(\d+)(?!.*\d)', path)
    #     if m:
    #         return path[:m.start(1)] + new_id_str + path[m.end(1):]
    #     return path

    # final_results[path_col] = final_results.apply(
    #     lambda row: replace_in_path(row[path_col], str(int(row["Sample_ID"]))),
    #     axis=1
    # )
    
    # final_results.to_csv(new_results_file, index=False)
    
    # Build a mapping from position to content
    file1_mapping = {i + 1: line for i, line in enumerate(lines)}
    file2_mapping = {i + 1: line for i, line in enumerate(lines1)}

    # Build a reverse mapping from content to position (handles duplicate content)
    file1_content_to_ids = {}
    for id_val, content in file1_mapping.items():
        if content not in file1_content_to_ids:
            file1_content_to_ids[content] = []
        file1_content_to_ids[content].append(id_val)
    
    file2_content_to_ids = {}
    for id_val, content in file2_mapping.items():
        if content not in file2_content_to_ids:
            file2_content_to_ids[content] = []
        file2_content_to_ids[content].append(id_val)
    
    # Find common content
    common_contents = set(lines) & set(lines1)

    # Build the mapping relationship (handles one-to-many cases)
    mapping = []
    for content in common_contents:
        file1_ids = file1_content_to_ids.get(content, [])
        file2_ids = file2_content_to_ids.get(content, [])

        # Simple handling: take the first matching ID (adjust as needed)
        if file1_ids and file2_ids:
            mapping.append((file1_ids[0], file2_ids[0]))
    
    mapping_df = pd.DataFrame(mapping, columns=["id_file1", "id_file2"])

    # Read the old results
    old_results = pd.read_csv(old_results_file)

    # Filter out the common rows
    old_common = old_results[old_results["Sample_ID"].isin([x[0] for x in mapping])].copy()

    # Merge mapping information
    old_common_with_mapping = old_common.merge(
        mapping_df, 
        left_on="Sample_ID", 
        right_on="id_file1", 
        how="inner"
    )
    
    # Update Sample_ID to the new ID
    new_generated = old_common_with_mapping.copy()
    new_generated["Sample_ID"] = new_generated["id_file2"]
    new_generated["Sample_ID_File1"] = new_generated["id_file1"]
    # Drop the temporary columns
    new_generated = new_generated.drop(["id_file1", "id_file2"], axis=1)

    # Reorder the columns to ensure Sample_ID_File1 is in the right position
    cols = new_generated.columns.tolist()
    if 'Sample_ID_File1' in cols:
        cols.remove('Sample_ID_File1')
        # Place Sample_ID_File1 right after Sample_ID
        sample_id_idx = cols.index('Sample_ID')
        cols.insert(sample_id_idx + 1, 'Sample_ID_File1')
        new_generated = new_generated[cols]

    # Handle the additional results file
    try:
        add_results = pd.read_csv(add_results_file)
        print(f"找到附加结果文件，行数: {len(add_results)}")

        # Ensure the additional results file has a Sample_ID_File1 column, add it if missing
        if 'Sample_ID_File1' not in add_results.columns:
            add_results['Sample_ID_File1'] = -1

        final_results = pd.concat([new_generated, add_results], ignore_index=True)
    except FileNotFoundError:
        print("未找到附加结果文件")
        final_results = new_generated

    # Data type cleanup
    if "Sample_ID" in final_results.columns:
        final_results = final_results.dropna(subset=["Sample_ID"])
        final_results["Sample_ID"] = final_results["Sample_ID"].astype(int)
    if "Sample_ID_File1" in final_results.columns:
        final_results["Sample_ID_File1"] = final_results["Sample_ID_File1"].fillna(-1).astype(int)

    # Path replacement logic
    path_col = final_results.columns[-1]
    print(f"检测到的路径列: {path_col}")

    def replace_in_path(path, new_id_str):
        if not isinstance(path, str):
            return path
        # Match common form: __123_output
        m = re.search(r'__(\d+)_output', path)
        if m:
            return re.sub(r'__(\d+)(_output)', f'__{new_id_str}\\2', path, count=1)
        # Match: _123_output
        m = re.search(r'_(\d+)_output', path)
        if m:
            return re.sub(r'_(\d+)(_output)', f'_{new_id_str}\\2', path, count=1)
        # Otherwise match the last number
        m = re.search(r'(\d+)(?!.*\d)', path)
        if m:
            return path[:m.start(1)] + new_id_str + path[m.end(1):]
        return path

    # Apply path replacement
    print("应用路径替换...")
    final_results[path_col] = final_results.apply(
        lambda row: replace_in_path(row[path_col], str(int(row["Sample_ID"]))),
        axis=1
    )
    
    # Verify the mapping relationship
    print("\n最终结果验证:")
    print(f"总行数: {len(final_results)}")
    print("前5行Sample_ID和Sample_ID_File1的对应关系:")
    for i, row in final_results.head().iterrows():
        print(f"  行{i}: Sample_ID={row['Sample_ID']}, Sample_ID_File1={row.get('Sample_ID_File1', 'N/A')}")
    
    # Save the results
    final_results.to_csv(new_results_file, index=False)
    
    
def func_return_value_labels_process(function_labels_file, mc_classify_file, mc_classify_function_labels_file):
    func_set = set()
    with open(function_labels_file, 'r', encoding='utf-8') as file:
        data = json.load(file)
        keys = list(data.keys())
        for key in keys: 
            func_set.add(key)
    # print(func_set)
            
    seq = 0
    label = '0'
    with open(mc_classify_function_labels_file, 'w', encoding='utf-8') as out:
        with open(mc_classify_file, 'r', encoding='utf-8') as mc_file:
            lines = mc_file.readlines()
            for line in lines:
                parts = line.strip().split(' ;; ')
                type = parts[4]
                src_line = parts[2]
                if type == 'Returning Function Call':
                    func_name = ''
                    print("line: ", line)
                    # Strip prefixes like 'return', '='
                    if '=' in src_line:
                        src_line = src_line.split('=', 1)[-1].strip()
                    # elif src_line.startswith('return '):
                    #     src_line = src_line[len('return '):].strip()
                    # Find the first "("
                    idx = src_line.find('(')
                    if idx >=0:
                        # Extract the likely function name part
                        func_name = src_line[:idx].strip()
                    else:
                        print("Error: function name parsed error!")    
                    print("function_name: ", func_name)
                    if func_name != '' and func_name in func_set:
                        print("has been labeled!")
                        label = 'return value of '+func_name+' is the critical variable'
                    else:
                        label = '0'
                # elif type == 'Other':
                #     if '(' in src_line and ')' in src_line:
                #         idx = src_line.find('(')
                #         if idx >=0:
                #             # Extract the likely function name part
                #             func_name = src_line[:idx].strip()
                #         else:
                #             print("Error: function name parsed error!") 
                #         if func_name != '' and func_name in func_set:
                #             print("has been labeled!")
                #         label = 'return value of '+func_name+' is the critical variable'
                else:
                    label = '0'
                out.write(str(seq+1)+':'+label+'\n')
                seq += 1


def find_function_name(file_path, line_number):

    FUNC_PREFIXES = (
        "static", "inline", "noinline", "const", "unsigned",
        "signed", "struct", "union", "enum", "extern",
        "int", "long", "short", "char", "void", "__init",
        "__maybe_unused", "__always_inline"
    )

    extract_name = re.compile(r'([A-Za-z_]\w*)\s*\(')

    current_func = None
    pending_decl = []
    in_decl = False

    def looks_like_decl_start(s):
        tokens = s.split()
        if not tokens:
            return False
        return tokens[0] in FUNC_PREFIXES

    def is_function_call(s):
        """Check whether this is a function call"""
        if s.endswith(";") and "(" in s and ")" in s:
            return True
        if "=" in s:
            return True
        if "->" in s or "." in s:
            return True
        return False

    def is_macro(s):
        """Macros must be skipped"""
        return s.startswith("#") or s.startswith("static DEVICE_ATTR")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            # Skip macros
            if is_macro(line):
                continue

            # Start collecting the function definition
            if not in_decl and "(" in line and looks_like_decl_start(line):

                # Don't allow a function call to be treated as a declaration (fixes the issue encountered)
                if is_function_call(line):
                    pass
                else:
                    in_decl = True
                    pending_decl = [line]
                continue

            # Currently inside function declaration mode
            if in_decl:
                pending_decl.append(line)

                # Encountered { -> this is a function definition
                if "{" in line:
                    decl = " ".join(pending_decl)
                    m = extract_name.search(decl)
                    if m:
                        current_func = m.group(1)

                    in_decl = False
                    pending_decl.clear()
                    continue

                # Encountered ; -> this is a declaration, not a definition
                if line.endswith(";"):
                    in_decl = False
                    pending_decl.clear()
                    continue

                continue

            # Found the target line
            if idx == line_number:
                return current_func, raw_line.rstrip("\n")

    return current_func, None

def find_function_bounds(new_file, func_name):
    """
    Find the start and end line of the function named func_name in new_file (by counting { }).
    Returns (start_line, end_line), or (None, None) if not found.
    """
    start = None
    brace = 0
    with open(new_file, "r", encoding="utf-8", errors="ignore") as f:
        for idx, raw in enumerate(f, start=1):
            line = raw.strip()
            # Simple detection of the function definition
            # Only match "func_name(" followed later by {
            if start is None:
                # This line might be the definition line
                if re.search(r'\b{}\s*\('.format(re.escape(func_name)), line):
                    # Possible start of the definition
                    # But we actually start counting braces once we see "{"
                    if '{' in line:
                        start = idx
                        # Count the { on this line
                        brace += line.count('{') - line.count('}')
                    else:
                        # Definition spans multiple lines, keep looking for {
                        start = idx
                continue
            else:
                # Already inside the function body
                brace += line.count('{') - line.count('}')
                if brace == 0:
                    # Function ends
                    end = idx
                    return start, end
    return None, None

def analyze_in_new_kernel(old_file, old_line_number, old_code, new_file, target_var):
    """
    old_file: relative (or absolute) file path in the old kernel
    old_line_number: line number in the old kernel file
    new_kernel_root: root directory of the new kernel source (absolute path)
    target_var: the variable name (string) to check, i.e. whether if (target_var ...) appears
    """
    
    ### debug
    # if old_file == '../data/kernel-code/linux-4.20-rc5/drivers/gpu/drm/panel/panel-raspberrypi-touchscreen.c':
    #     print('*'*65)
    
    # 1. Find the function name and exact code for that line in the old kernel
    old_func, _ = find_function_name(old_file, old_line_number)
    if old_func is None:
        # print("不能找到旧内核对应的函数名称")
        return

    # print(f"旧内核: 函数 {old_func}，旧行 {old_line_number} 内容: `{old_code}`")

    # 2. Locate the corresponding file in the new kernel tree
    # Assume old_file is relative to the kernel tree root (or you've already built the path yourself)
    # new_file = os.path.join(new_kernel_root, old_file)
    if not os.path.isfile(new_file):
        # print("在新内核里找不到文件:", new_file)
        return

    # 3. Find the start and end line of that function in the new kernel
    start, end = find_function_bounds(new_file, old_func)
    if start is None:
        # print("在新内核里找不到函数定义:", old_func)
        return

    # print(f"在新内核里函数 `{old_func}` 大致定义区间: 行 {start} - {end}")

    # 4. Read the new function body, look for a statement "similar" to old_code, and a subsequent if (target_var ...)
    matches = []
    with open(new_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Normalize old_code for comparison against the new lines (adjustable)
    old_norm = old_code.strip()

    for lineno in range(start - 1, end):  # Python indices start from 0
        new_line = lines[lineno].rstrip("\n")
        if new_line.strip() == old_norm:
            matches.append(lineno + 1)  # store the line number

    if not matches:
        # print("在新函数中没有找到完全相同的语句:", old_norm)
        return

    # print("找到匹配语句所在新内核行：", matches)

    # 5. For each matching line, scan forward a number of lines (e.g. within 50) to check for an if that tests target_var
    for mline in matches:
        found_if = False
        scan_end = min(end, mline + 200)  # scan up to 200 lines ahead, tunable
        for check_lineno in range(mline, scan_end):
            line_text = lines[check_lineno].strip()
            # Simple check for if (target_var ...)
            # A more complex parser could be added here, e.g. a regex matching only if statements
            if "if" in line_text and '(' in line_text and target_var in line_text:
            # if re.match(rf'if\s*\(\s*{re.escape(target_var)}\b', line_text):
                # print(f"旧内核: 文件 {old_file}, 函数 {old_func}，旧行 {old_line_number} 内容: `{old_code}`")
                # print(f"在新内核里: 文件 {new_file} 函数 `{old_func}` 大致定义区间: 行 {start} - {end}")
                # print("找到匹配语句所在新内核行：", matches)
                # print(f"在匹配行之后 (new line {check_lineno+1}) 发现 if 检查: `{line_text}`")
                found_if = True
                break
        # if not found_if:
        #     print(f"在匹配行 {mline} 之后，没有在 {mline+1} 到 {scan_end} 行范围内找到 if 检查 `{target_var}`")
        return found_if

    return False

def compare_kernel_code(src_path, src_path_1, bug_list_path):
    with open('../data/paper-results/kernel_old_new_compare_results.csv', 'w', encoding='utf-8') as write_file:
        with open(bug_list_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            seq = 0
            for line in lines:
                line = line.strip()
                line_parts = line.split(' ;; ')
                type = line_parts[4]
                file_path = line_parts[0].strip().split('linux-4.20-rc5/')[1]
                line_no = line_parts[1].strip()
                target_line = line_parts[2].strip()
                if type == 'Returning Function Call' and '=' in target_line:
                    cv = target_line.split('=')[0]
                    # func, _ = find_function_name(line_parts[0].strip(), int(line_no))
                    new_kernel_path = '../data/kernel-code/linux-6.18-rc5/'+file_path
                    flag = analyze_in_new_kernel(line_parts[0].strip(), int(line_no), target_line, new_kernel_path, cv.strip())
                    flag1 = analyze_in_new_kernel(line_parts[0].strip(), int(line_no), target_line, line_parts[0].strip(), cv.strip())
                    if flag:
                        # print(seq, flag)
                        write_file.write(str(seq+1)+'\t1\n')
                    else:
                        write_file.write(str(seq+1)+'\t0\n')
                    if flag1:
                        print(str(seq+1)+'\tHas been checked')
                    else:
                        print(str(seq+1)+'\tunknown')
                else:
                    write_file.write(str(seq+1)+'\t0\n')
                    print(str(seq+1)+'\tunknown')
                seq += 1
                    # print(file_path, line_no, cv, func)
                    # 
                    # if not os.path.isfile(new_kernel_path):
                    #         print("在新内核里找不到文件:", new_kernel_path)
                    #         return
                    # with open(new_kernel_path, 'r', encoding='utf-8') as new_file:

def analyze_fixed_bug(fixed_array, bug_list_path):
    seq = 1 
    with open(bug_list_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip()
            line_parts = line.split(' ;; ')
            type = line_parts[4]
            file_path = line_parts[0].strip().split('linux-4.20-rc5/')[1]
            line_no = line_parts[1].strip()
            target_line = line_parts[2].strip() 
            if seq in fixed_array:
                print(file_path+'@'+line_no+'@'+type+'@'+target_line)
            seq = seq + 1


def analyze_subsystem_distribution(mc_path, sc_path, bug_path):
    """
    Analyze subsystem distribution from mc, sc, and bug_list classify files.

    Args:
        mc_path: path to mc_classify.list
        sc_path: path to sc_classify.list
        bug_path: path to bug_list_0.15_classify.list
    """

    def extract_subsystem(file_path_str):
        """
        Extract first-level subsystem directory from file path.
        E.g., ../data/kernel-code/linux-4.20-rc5/drivers/tty/serial/max310x.c
        -> drivers
        """
        match = re.search(r'linux-[\d\.\-rc]+/([^/]+)', file_path_str)
        if match:
            return match.group(1)
        return None

    mc_sc_subsystem_counts = {}
    bug_subsystem_counts = {}

    # Process mc_classify.list and sc_classify.list together
    for file_path in [mc_path, sc_path]:
        if not os.path.exists(file_path):
            print(f"[Warning] File not found: {file_path}")
            continue

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Format: path ;; lineno ;; code ;; context ;; type
                parts = line.split(' ;; ')
                if len(parts) < 1:
                    continue

                file_path_str = parts[0].strip()
                subsystem = extract_subsystem(file_path_str)

                if subsystem:
                    if subsystem in mc_sc_subsystem_counts:
                        mc_sc_subsystem_counts[subsystem] += 1
                    else:
                        mc_sc_subsystem_counts[subsystem] = 1

    # Process bug_list_0.15_classify.list separately
    if os.path.exists(bug_path):
        with open(bug_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Format: path ;; lineno ;; code ;; context ;; type
                parts = line.split(' ;; ')
                if len(parts) < 1:
                    continue

                file_path_str = parts[0].strip()
                subsystem = extract_subsystem(file_path_str)

                if subsystem:
                    if subsystem in bug_subsystem_counts:
                        bug_subsystem_counts[subsystem] += 1
                    else:
                        bug_subsystem_counts[subsystem] = 1
    else:
        print(f"[Warning] File not found: {bug_path}")

    # Print results
    print("\n" + "="*80)
    print("SUBSYSTEM DISTRIBUTION ANALYSIS")
    print("="*80)

    # MC + SC combined statistics
    print("\n[MC + SC Combined] Sample count per subsystem:")
    print("-" * 80)
    sorted_mc_sc = sorted(mc_sc_subsystem_counts.items(), key=lambda x: x[1], reverse=True)
    total_mc_sc = sum(mc_sc_subsystem_counts.values())

    for subsystem, count in sorted_mc_sc:
        percentage = (count / total_mc_sc * 100) if total_mc_sc > 0 else 0
        print(f"  {subsystem:60s} : {count:5d} ({percentage:5.2f}%)")
    print(f"\n  Total MC+SC samples: {total_mc_sc}")

    # Bug list statistics (separate)
    print("\n[Bug List 0.15] Sample count per subsystem:")
    print("-" * 80)
    sorted_bug = sorted(bug_subsystem_counts.items(), key=lambda x: x[1], reverse=True)
    total_bug = sum(bug_subsystem_counts.values())

    for subsystem, count in sorted_bug:
        percentage = (count / total_bug * 100) if total_bug > 0 else 0
        print(f"  {subsystem:60s} : {count:5d} ({percentage:5.2f}%)")
    print(f"\n  Total Bug List samples: {total_bug}")

    print("\n" + "="*80) 
    
    
                  
                    
        


if __name__ == '__main__':
    
    input_dir = '../data/paper-results'
    src_path = '../data/kernel-code/linux-4.20-rc5'
    src_path_1 = '../data/kernel-code/linux-6.18-rc5'
    bug_path_0 = '../data/crix-results/results-4.20-rc5-1/results-0.15'
    bug_path_2 = '../data/crix-results/results-4.20-rc5-1/results-0.25'
    bug_path_1 = '../data/crix-results/results-4.20-rc5-1/results-0.20'
    llm_results_path = '../data/output_results/'

    ### mc/sc data analysis
    ###********************************************
    ### get checked use data list
    get_checked_list('checked_use_selected_400.list') # old: checked_use_selected.list
    checked_list_path = os.path.join(input_dir, 'checked_use_selected_verified.list') # old: checked_use_selected_verified.list
    output_checked_path = os.path.join(input_dir, 'sc.list') # old: sc.list
    process_checked_use_selected(checked_list_path, src_path, output_checked_path)
    get_type_function_bug(src_path, os.path.join(input_dir, 'sc.list'), os.path.join(input_dir, 'sc_classify.list'), os.path.join(input_dir, 'sc_classify_full_contexts.list'))
    
    ### bug list analysis
    ###*******************************************
    ## process argmt json file
    process_argmt_json_like_file(bug_path_0, src_path)
    merge_list_files(bug_path_0, os.path.join(bug_path_0, "bug_list_0.15.txt"))

    ## bug list type function
    input_path_bug = '../data/crix-results/results-4.20-rc5-1/results-0.15/bug_list_0.15.txt'
    output_path_bug = '../data/crix-results/results-4.20-rc5-1/results-0.15/bug_list_0.15_classify_test.list'
    output_path_bug_full = '../data/crix-results/results-4.20-rc5-1/results-0.15/bug_list_0.15_classify_full_contexts_test.list'
    output_path_bug_line_type = '../data/crix-results/results-4.20-rc5-1/results-0.15/bug_list_0.15_classify_line_type_test.csv'
    get_type_function_bug(src_path, input_path_bug, output_path_bug, output_path_bug_full, output_path_bug_line_type)
    
    ## get paper ground truth
    get_paper_results(input_dir, src_path)
    # paper and bug list matched labels
    ## 0: bug_list_0.15.txt: no classify, #1: bug_list_0.15_classify.list: classify #2: bug_list_0.15_classify_full_contexts.list: with classify full contexts
    match_paper_report_results_classify_label(bug_path_1, os.path.join(input_dir, 'matched_before_after_use_10.list'), os.path.join(bug_path_0, 'bug_list_0.15_classify_full_contexts.list'), 2) 
    
    ## compare bug list 0.15/0.20/0.25 and new/old
    compare_old_new_bug_list(bug_path_1+'/bug_list_0.20_classify.list', bug_path_2+'/bug_list_0.25_classify.list', bug_path_2)

    ## get old bug list results
    generate_new_bug_list_results(bug_path_0+'/bug_list_0.15_classify.list', bug_path_1+'/bug_list_0.20_classify.list', llm_results_path+'/bug_list_0.15_COT_claude-sonnet-4-20250514-new.csv', llm_results_path+'/bug_list_0.2_COT_claude-sonnet-4-20250514-newadd.csv', llm_results_path+'/bug_list_0.2_COT_claude-sonnet-4-20250514-new.csv')

    ## static analysis results process
    ##*******************************************
    func_return_value_labels_process(os.path.join(input_dir, 'function_return_value_labels.json'), os.path.join(input_dir, 'sc_classify.list'), os.path.join(input_dir, 'sc_classify_function_labels.list'))

    ## linux-4.20-rc5 and linux-6.18-rc5 compare
    bug_list_path = os.path.join(input_dir, 'bug_list_0.15_classify.list')
    compare_kernel_code(src_path, src_path_1, bug_list_path)
    new_fixed_list = [
        137, 1308, 1414, 1438, 1556, 1589, 1745, 1774, 1813, 1894,
        1949, 2034, 2041, 2069, 2110, 2132, 2140, 2181, 2232, 2264,
        2265, 2295, 2313, 2327, 2342
    ]
    analyze_fixed_bug(new_fixed_list, os.path.join(bug_path_0, 'bug_list_0.15_classify.list'))
    
    ## subsystem distribution analysis (mc+sc, bug_list)
    ##********************************************
    mc_classify_path = os.path.join(input_dir, 'mc_classify.list')
    sc_classify_path = os.path.join(input_dir, 'sc_classify.list')
    bug_list_path = os.path.join(input_dir, 'bug_list_0.15_classify.list')
    analyze_subsystem_distribution(mc_classify_path, sc_classify_path, bug_list_path)
    