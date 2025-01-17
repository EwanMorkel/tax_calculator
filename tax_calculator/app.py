from flask import Flask, render_template, request, redirect, url_for
import os
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST': 
        try:
            # Get form data
            data = request.form.to_dict()
            logging.debug(f"Form data: {data}")
            # Process data and calculate results
            results = calculate_results(data)
            logging.debug(f"Calculated results: {results}")
            # Render report template with results
            rendered = render_template('report.html', results=results)
            logging.debug(f"Rendered HTML: {rendered[:500]}...")  # Log the first 500 characters of the rendered HTML
            return rendered
        except Exception as e:
            logging.error(f"Error generating report: {e}")
            return f"An error occurred: {e}", 500
    return render_template('index.html')

def calculate_results(data):
    # Extract and process data from form
    filing_status = int(data.get('filing_status'))
    num_jobs_user = int(data.get('num_jobs_user', 0))
    num_jobs_spouse = int(data.get('num_jobs_spouse', 0))

    age_list_user = [int(data.get(f'earnings_user_{i+1}', 0)) for i in range(num_jobs_user)]
    pay_periods_list_user = [int(data.get(f'pay_periods_user_{i+1}', 0)) for i in range(num_jobs_user)]
    tax_withheld_list_user = [float(data.get(f'tax_withheld_user_{i+1}', 0)) for i in range(num_jobs_user)]

    age_list_spouse = [int(data.get(f'earnings_spouse_{i+1}', 0)) for i in range(num_jobs_spouse)]
    pay_periods_list_spouse = [int(data.get(f'pay_periods_spouse_{i+1}', 0)) for i in range(num_jobs_spouse)]
    tax_withheld_list_spouse = [float(data.get(f'tax_withheld_spouse_{i+1}', 0)) for i in range(num_jobs_spouse)]

    total_tax_withheld_user = sum(pay_periods * tax_withheld for pay_periods, tax_withheld in zip(pay_periods_list_user, tax_withheld_list_user))
    total_tax_withheld_spouse = sum(pay_periods * tax_withheld for pay_periods, tax_withheld in zip(pay_periods_list_spouse, tax_withheld_list_spouse))
    total_tax_withheld = total_tax_withheld_user + total_tax_withheld_spouse

    additional_tax_payments = float(data.get('estimated_tax_payments', 0))
    total_tax_withheld += additional_tax_payments

    hsa_and_401k = int(data.get('hsa_and_401k', 0))
    retirement_contributions = int(data.get('retirement_contributions', 0)) if hsa_and_401k == 1 else 0

    net_rental_income = max(0, float(data.get('net_rental_income', 0)))
    interest_income = float(data.get('interest_income', 0))
    short_term_capital_gain_income = float(data.get('short_term_capital_gain_income', 0))
    miscellaneous_ordinary_income = float(data.get('miscellaneous_ordinary_income', 0))

    if filing_status == 1:
        standard_deduction = 15000
    elif filing_status == 2:
        standard_deduction = 30000
    elif filing_status == 3:
        standard_deduction = 22500

    Total_earnings_user = sum(age_list_user)
    Total_earnings_spouse = sum(age_list_spouse)
    Total_earnings = Total_earnings_user + Total_earnings_spouse

    total_additional_income = net_rental_income + interest_income + short_term_capital_gain_income + miscellaneous_ordinary_income
    Taxable_Income = Total_earnings + total_additional_income - standard_deduction - retirement_contributions

    # Ensure Taxable_Income is not negative
    Taxable_Income = max(Taxable_Income, 0)

    tax_brackets_single = [
        (0, 11925, 0.10, 0),
        (11925, 48475, 0.12, 1193),
        (48475, 103350, 0.22, 5579),
        (103350, 197300, 0.24, 17651),
        (197300, 250525, 0.32, 40199),
        (250525, 626350, 0.35, 57231),
        (626350, float('inf'), 0.37, 188770)
    ]

    tax_brackets_married = [
        (0, 23850, 0.10, 0),
        (23850, 96950, 0.12, 2385),
        (96950, 206700, 0.22, 11157),
        (206700, 394600, 0.24, 35302),
        (394600, 501050, 0.32, 80398),
        (501050, 751600, 0.35, 114462),
        (751600, float('inf'), 0.37, 202155)
    ]

    tax_brackets_head_of_household = [
        (0, 17000, 0.10, 0),
        (17000, 64850, 0.12, 1700),
        (64850, 103350, 0.22, 7442),
        (103350, 197300, 0.24, 15912),
        (197300, 250500, 0.32, 38460),
        (250500, 626350, 0.35, 55484),
        (626350, float('inf'), 0.37, 187032)
    ]

    if filing_status == 1:
        tax_brackets = tax_brackets_single
    elif filing_status == 2:
        tax_brackets = tax_brackets_married
    elif filing_status == 3:
        tax_brackets = tax_brackets_head_of_household

    def calculate_tax(income, tax_brackets):
        tax = 0
        for bracket in tax_brackets:
            if income > bracket[1]:
                tax += (bracket[1] - bracket[0]) * bracket[2]
            else:
                tax += (income - bracket[0]) * bracket[2]
                break
        return tax

    total_tax = calculate_tax(Taxable_Income, tax_brackets)

    def sstaxvalue(n):
        if n > 176100:
            return 176100 * 0.062
        else:
            return n * 0.062

    total_sstax_user = sum(sstaxvalue(age) for age in age_list_user)
    total_sstax_spouse = sum(sstaxvalue(age) for age in age_list_spouse)

    if Total_earnings_user > 176100:
        sstaxliability_user = 176100 * 0.062
    else:
        sstaxliability_user = Total_earnings_user * 0.062

    if Total_earnings_spouse > 176100:
        sstaxliability_spouse = 176100 * 0.062
    else:
        sstaxliability_spouse = Total_earnings_spouse * 0.062

    sstaxcredit_user = abs(sstaxliability_user - total_sstax_user)
    sstaxcredit_spouse = abs(sstaxliability_spouse - total_sstax_spouse)

    def calculate_ctc(num_children, taxable_income, filing_status):
        ctc_per_child = 2000
        phase_out_threshold = 200000 if filing_status == 1 else 400000
        phase_out_rate = 50 / 1000

        total_ctc = num_children * ctc_per_child
        excess_income = taxable_income + standard_deduction - phase_out_threshold

        if excess_income > 0:
            phase_out_amount = excess_income * phase_out_rate
            total_ctc -= phase_out_amount

        return max(total_ctc, 0)

    num_children = int(data.get('num_children', 0))
    child_tax_credit = calculate_ctc(num_children, Taxable_Income, filing_status)

    medicare_threshold = 200000 if filing_status in [1, 3] else 250000
    additional_medicare_tax = 0.009 * max(0, Total_earnings - medicare_threshold)

    tax_balance = total_tax + additional_medicare_tax - total_tax_withheld - sstaxcredit_user - sstaxcredit_spouse - child_tax_credit

    return {
        'total_earnings': Total_earnings,
        'taxable_income': Taxable_Income,
        'total_income_tax': total_tax,
        'total_ss_tax_user': total_sstax_user,
        'total_ss_tax_spouse': total_sstax_spouse,
        'ss_tax_credit_user': sstaxcredit_user,
        'ss_tax_credit_spouse': sstaxcredit_spouse,
        'total_tax_withheld': total_tax_withheld,
        'child_tax_credit': child_tax_credit,
        'additional_medicare_tax': additional_medicare_tax,
        'tax_balance': tax_balance
    }

if __name__ == '__main__':
    app.run(debug=True)