import itertools

import numpy as np
import pandas as pd
import rpy2.robjects as ro
from rpy2.robjects import pandas2ri, Formula, numpy2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr

lmerTest = importr('lmerTest')
emmeans = importr('emmeans')
stats = importr("stats")
Matrix = importr("Matrix")
nlme = importr("nlme")
lme4 = importr("lme4")


# ---------------------------------
# ----------> For USERS >----------
# ---------------------------------

# ---------------------------------
# Step 1/5: Select SUBSET!!!
# ---------------------------------

# Read .csv data (it can accept formats like .xlsx, just chagne pd.read_XXX)
data = pd.read_csv("Data_Experiment.csv", encoding="utf-8")


# ---------------------------------
# Step 2/5: Select SUBSET!!!
# ---------------------------------

# Note: If you do not want to select subset,
# delete the line(s) you do not need, or press ctrl+/ annotating the line(s).

# determine subset based on "condition==value"
# data = data[(data['exp_type'] == "exp1")]# & (data['ifanimal'] == True)]

# Preserve data only within 2.5 * SD
mean_rt = data['rt'].mean()
std_rt = data['rt'].std()
data = data[(data['rt'] > (mean_rt - 2.5 * std_rt)) & (data['rt'] < (mean_rt + 2.5 * std_rt))]

data = data[(data['ifanimal'] == False)]

data = data[data['ifcorr'] == 1]  # rt data works on ACC = 1

data['rt'] = data['rt'] * 1000  # if rt is in ms, * 1000 might be better


# ---------------------------------
# Step 3/5: Code your variables!!!
# ---------------------------------

# * Optional for categorical variables
# ** Should-do for ordinal variables
# *** must-do for continuous variables

# I adopted Orthogonal Polynomial Coding here:
# 2-level -> -0.5, 0.5
# 3-level -> -1, 0, 1
# 4-level -> -0.671, -0.224, 0.224, 0.671 (not sure why it is like this)

# Ref:
# https://online.stat.psu.edu/stat502/lesson/10/10.2
# https://stats.oarc.ucla.edu/spss/faq/coding-systems-for-categorical-variables-in-regression-analysis/

data['Tpriming'] = -0.5 * (data['priming'] == "priming") + 0.5 * (data['priming'] != "priming")
data['Tsyl'] = -0.5 * (data['syl'] == 2) + 0.5 * (data['syl'] != 2)
data['Texp_type'] = -0.5 * (data['exp_type'] == "exp1") + 0.5 * (data['exp_type'] != "exp1")
# data["Tifanimal"] = -0.5 * (data['ifanimal'] == True) + 0.5 * (data['ifanimal'] != True)

# ---------------------------------
# Step 4/5: Write your variables and create Formula
# ---------------------------------

dep_var = "rt"
fixed_factor = ["Tpriming", "Tsyl", "Texp_type"]
random_factor = ["sub", "word"]

# ---------------------------------
# ABOVE IS OK. DO NOT TOUCH BELOW.
# ---------------------------------

fixed_str = " * ".join(fixed_factor)
fixed_combo = []
for i in range(len(fixed_factor), 0, -1):  # 从1开始，因为0会生成空集
    for combo in itertools.combinations(fixed_factor, i):
        fixed_combo.append(":".join(combo))


# ---------------------------------
# Step 5/5 [Optional]: If you want to skip a few formulas
# ---------------------------------

prev_formula = "rt ~ Tpriming * Tsyl * Texp_type + (1 + Texp_type | sub) + (1 | word)"#"rt ~ Tpriming * Tsyl * Texp_type + (1 + Texp_type | sub) + (1 | word)"  # "rt ~ Tpriming * Tsyl * Texp_type + (1 + Texp_type | sub) + (1 | word)"


# ---------------------------------
# ----------< For USERS <----------
# ---------------------------------

if prev_formula:
    random_model = {kw[1]: kw[0].split(" + ") for kw in [full_item.split(")")[0].split(" | ") for full_item in prev_formula.split("(1 + ")[1:]]}
    for key in random_factor:
        try:
            random_model[key]
        except KeyError:
            random_model[key] = []
else:
    random_model = {key: fixed_combo[:] for key in random_factor}

# Change pandas DataFrame into R language's data.frame
with (ro.default_converter + pandas2ri.converter).context():
    r_data = ro.conversion.get_conversion().py2rpy(data)
while True:
    random_str = ""
    for key in random_model:
        if not random_model[key]:  # has no element
            random_str += "(1" + f" | {key}) + "
        else:  # has element
            random_str += "(1 + " + " + ".join(random_model[key]) + f" | {key}) + "
    random_str = random_str.rstrip(" + ")

    formula_str = f"{dep_var} ~ {fixed_str} + {random_str}"
    formula = Formula(formula_str)
    print(f"Running FORMULA: {formula_str}")

    # 使用lmer函数拟合模型
    model1 = lmerTest.lmer(formula, REML=True, data=r_data, control=lme4.lmerControl("bobyqa"))
    summary_model1_r = Matrix.summary(model1)
    with localconverter(ro.default_converter + pandas2ri.converter + numpy2ri.converter):
        summary_model1 = ro.conversion.get_conversion().rpy2py(summary_model1_r)
    try:
        isWarning = eval(str(summary_model1["optinfo"]["conv"]['lme4']["messages"]).strip("o"))
    except KeyError:
        isWarning = False

    # Transform random table to DataFrame format
    random_table = []
    corrs_supp = []
    lines = str(nlme.VarCorr(model1)).strip().split('\n')
    # print(lines)
    for line in lines[1:]:  # Exclude the 1st
        # Check if the 2nd element is number
        elements = line.strip().split()
        if not elements:
            continue
        if elements[0].split(".")[0].strip("-").isnumeric():
            corrs_supp.extend([float(e) if e.split(".")[0].strip("-").isnumeric() else e for e in elements])
            continue
        # print(elements)
        if elements[1].strip("-").split(".")[0].isnumeric():
            elements = [Groups] + elements
        else:
            Groups = elements[0]
        elements = [float(e) if e.split(".")[0].strip("-").isnumeric() else e for e in elements]
        # print(elements[0], elements[1])
        if elements[1] == "Residual":
            break

        random_table.append(elements)
        # print(elements)

    df = pd.DataFrame(random_table)

    df = df[df[1] != '(Intercept)']  # ignore all the "(intercept)"

    # print(df)
    # Check if there is any corr item that is >= 0.90
    all_corrs = np.array(df.iloc[:, 3:].dropna(how="all")).flatten().tolist()
    all_corrs = [corr for corr in all_corrs if isinstance(corr, (int, float))]
    all_corrs.extend(corrs_supp)

    # print(all_corrs)
    isTooLargeCorr = any(corr >= .9 for corr in all_corrs)

    isGoodModel = not isWarning and not isTooLargeCorr

    if isGoodModel:
        print(f"Formula {formula_str} is a good model.")
        break
    else:
        rf2ex = df.loc[df[2].idxmin(0)][0]
        ff2ex = df.loc[df[2].idxmin(0)][1]

        print(f"Exclude random model item: {ff2ex} | {rf2ex}")

        # Processing EXCLUSION
        random_model[rf2ex].remove(ff2ex)
        # print(random_model)
        print("---\n---")
    # time.sleep(5)
    # ('methTitle', 'objClass', 'devcomp', 'isLmer', 'useScale', 'logLik', 'family', 'link', 'ngrps', 'coefficients', 'sigma', 'vcov', 'varcor', 'AICtab', 'call', 'residuals', 'fitMsgs', 'optinfo', 'corrSet')
    # ('optimizer', 'control', 'derivs', 'conv', 'feval', 'message', 'warnings', 'val')
    if not any(random_model.values()):
        print("Every model failed")
        break
print(summary_model1_r)
anova_model1 = stats.anova(model1, type=3, ddf="Kenward-Roger")

# anova_model1 change format
print(anova_model1)

with (ro.default_converter + pandas2ri.converter).context():
    anova_model1 = ro.conversion.get_conversion().rpy2py(anova_model1)

# print(anova_model1["Pr(>F)"])

# model1 = lmerTest.lmer(Formula("rt ~ Tpriming * Tsyl + (1 | sub) + (1 | word)"), REML=True, data=r_data)
# summary_model1_r = Matrix.summary(model1)
# print(summary_model1_r)
if isGoodModel:
    print(f"Found good model")
else:
    print(f"Found no good model")

emmeans_result = emmeans.emmeans(model1, specs="Tsyl:Tpriming")
print(emmeans_result)
emmeans_result = emmeans.emmeans(model1, specs="Tpriming:Tsyl")
print(emmeans_result)

print(f"Last formula is {formula_str}\n\n")
print("-------------------------------------------------------")
print("SCRIPT End √ | Ignore \"R[write to console]\" down below, as it is an automatic callback")
print("-------------------------------------------------------")

