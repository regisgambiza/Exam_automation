from question_rater import run_mcq_debate

# Test Quick mode
run_mcq_debate(
    input_file="questions_database.json", 
    output_file="results_quick.json", 
    mode="quick"
)
print("Quick mode results saved to results_quick.json")

# Test In-depth mode
run_mcq_debate(
    input_file="questions_database.json", 
    output_file="results_indepth.json", 
    mode="in-depth"
)
print("In-depth mode results saved to results_indepth.json")
