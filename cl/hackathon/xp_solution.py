# Copyright (C) 2023-present The Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass
from typing import Any
from cl.runtime import Context
from cl.runtime.experiments.trial_key import TrialKey
from cl.runtime.log.exceptions.user_error import UserError
from cl.runtime.primitive.float_util import FloatUtil
from cl.runtime.records.dataclasses_extensions import missing
from cl.convince.llms.gpt.gpt_llm import GptLlm
from cl.convince.llms.llm import Llm
from cl.convince.llms.llm_key import LlmKey
from cl.convince.retrievers.retriever_util import RetrieverUtil
from cl.tradeentry.entries.date_entry import DateEntry
from cl.tradeentry.entries.number_entry import NumberEntry
from cl.hackathon.hackathon_input import HackathonInput
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_solution import HackathonSolution


@dataclass(slots=True, kw_only=True)
class XpSolution(HackathonSolution):
    """Solution based on extracting values in one step."""

    prompt: str = missing()
    """One step prompt to parse trade."""

    llm_2: LlmKey = missing()
    """Second LLM to use"""

    verification_prompt: str = missing()
    """Prompt used to verify and correct results if differences arise"""

    def score_output(self, output_: HackathonOutput) -> None:

        if Context.current().trial is not None:
            raise UserError("Cannot override TrialId that is already set, exiting.")  # TODO: Append?

        with Context(full_llm=self.llm, trial=TrialKey(trial_id=str(output_.trial_id))) as context:

            # Load the full LLM specified by the context
            llm = context.load_one(Llm, context.full_llm)
            llm2 = context.load_one(Llm, self.llm_2)
            query = self.prompt.format(input_text=output_.entry_text)

            output = llm.completion(query)
            json_output = RetrieverUtil.extract_json(output) or {}

            query2 = "You are a challenger to the responses from another trade inputer. \n" + query
            output2 = llm2.completion(query2)
            json_output2 = RetrieverUtil.extract_json(output2) or {}

            diffs = self._compare_dicts(json_output, json_output2)
            print("diffs", diffs)

            if len(diffs) > 0:
                formatted_diffs = self._format_field_list(diffs, json_output, json_output2)
                verification_query = self.verification_prompt.format(input_text=output_.entry_text, field_list=formatted_diffs)
                verification_output = llm.completion(verification_query)
                print("verification_query", verification_query)
                print("verification_output", verification_output)

                verification_json_output = RetrieverUtil.extract_json(verification_output)
                if verification_json_output is not None:
                    for k, v in verification_json_output.items():
                        if v == "<MISSING>":
                            json_output.pop(k, None)
                        else:
                            json_output[k] = v
                

            if json_output:

                # Effective date
                try:
                    effective_date = json_output.get("effective_date")
                    if effective_date is not None:
                        effective_date = DateEntry(text=str(effective_date))
                        effective_date.run_generate()
                        output_.effective_date = effective_date.date
                except Exception as e:
                    output_.effective_date = str(e)

                # Maturity date
                try:
                    maturity_date = json_output.get("maturity_date")
                    if maturity_date is not None:
                        maturity_date = DateEntry(text=str(maturity_date))
                        maturity_date.run_generate()
                        output_.maturity_date = maturity_date.date
                except Exception as e:
                    output_.maturity_date = str(e)

                # Tenor
                try:
                    tenor_years = json_output.get("tenor_years")
                    if isinstance(tenor_years, int):
                        output_.tenor_years = str(FloatUtil.to_int_or_float(tenor_years))
                    elif tenor_years is not None:
                        tenor_years = NumberEntry(text=str(tenor_years))
                        tenor_years.run_generate()
                        output_.tenor_years = str(FloatUtil.to_int_or_float(tenor_years.value))
                except Exception as e:
                    output_.tenor_years = str(e)

                # Pay leg notional
                try:
                    pay_leg_notional = json_output.get("pay_leg_notional")
                    if isinstance(pay_leg_notional, float):
                        output_.pay_leg_notional = str(FloatUtil.to_int_or_float(pay_leg_notional))
                    elif pay_leg_notional is not None:
                        pay_leg_notional = NumberEntry(text=str(pay_leg_notional))
                        pay_leg_notional.run_generate()
                        output_.pay_leg_notional = str(FloatUtil.to_int_or_float(pay_leg_notional.value))
                except Exception as e:
                    output_.pay_leg_notional = str(e)

                # Pay leg currency
                try:
                    pay_leg_ccy = json_output.get("pay_leg_ccy")
                    if isinstance(pay_leg_ccy, str):
                        output_.pay_leg_ccy = pay_leg_ccy
                except Exception as e:
                    output_.pay_leg_ccy = str(e)

                # Pay leg payment frequency
                try:
                    pay_leg_freq_months = json_output.get("pay_leg_freq_months")
                    if isinstance(pay_leg_freq_months, int):
                        output_.pay_leg_freq_months = str(FloatUtil.to_int_or_float(pay_leg_freq_months))
                    elif pay_leg_freq_months is not None:
                        pay_leg_freq_months_entry = NumberEntry(text=str(pay_leg_freq_months))
                        pay_leg_freq_months_entry.run_generate()
                        output_.pay_leg_freq_months = str(FloatUtil.to_int_or_float(pay_leg_freq_months_entry.value))
                except Exception as e:
                    output_.pay_leg_freq_months = str(e)

                # Pay leg basis
                try:
                    pay_leg_basis = json_output.get("pay_leg_basis")
                    if isinstance(pay_leg_basis, str):
                        output_.pay_leg_basis = pay_leg_basis
                except Exception as e:
                    output_.pay_leg_basis = str(e)

                # Pay leg floating interest rate index
                try:
                    pay_leg_float_index = json_output.get("pay_leg_float_index")
                    if isinstance(pay_leg_float_index, str):
                        output_.pay_leg_float_index = pay_leg_float_index
                except Exception as e:
                    output_.pay_leg_float_index = str(e)

                # Pay leg spread in basis points
                try:
                    pay_leg_float_spread_bp = json_output.get("pay_leg_float_spread_bp")
                    if isinstance(pay_leg_float_spread_bp, float):
                        output_.pay_leg_float_spread_bp = str(FloatUtil.to_int_or_float(pay_leg_float_spread_bp))
                    elif pay_leg_float_spread_bp is not None:
                        pay_leg_float_spread_bp = NumberEntry(text=str(pay_leg_float_spread_bp))
                        pay_leg_float_spread_bp.run_generate()
                        output_.pay_leg_float_spread_bp = str(FloatUtil.to_int_or_float(pay_leg_float_spread_bp.value))
                except Exception as e:
                    output_.pay_leg_float_spread_bp = str(e)

                # Pay leg fixed rate in percent
                try:
                    pay_leg_fixed_rate_pct = json_output.get("pay_leg_fixed_rate_pct")
                    if isinstance(pay_leg_fixed_rate_pct, float):
                        output_.pay_leg_fixed_rate_pct = str(FloatUtil.to_int_or_float(pay_leg_fixed_rate_pct))
                    elif pay_leg_fixed_rate_pct is not None:
                        pay_leg_fixed_rate_pct = NumberEntry(text=str(pay_leg_fixed_rate_pct))
                        pay_leg_fixed_rate_pct.run_generate()
                        output_.pay_leg_fixed_rate_pct = str(FloatUtil.to_int_or_float(pay_leg_fixed_rate_pct.value))
                except Exception as e:
                    output_.pay_leg_fixed_rate_pct = str(e)

                # Receive leg notional
                try:
                    rec_leg_notional = json_output.get("rec_leg_notional")
                    if isinstance(rec_leg_notional, float):
                        output_.rec_leg_notional = str(FloatUtil.to_int_or_float(rec_leg_notional))
                    elif rec_leg_notional is not None:
                        rec_leg_notional = NumberEntry(text=str(rec_leg_notional))
                        rec_leg_notional.run_generate()
                        output_.rec_leg_notional = str(FloatUtil.to_int_or_float(rec_leg_notional.value))
                except Exception as e:
                    output_.rec_leg_notional = str(e)

                # Receive leg currency
                try:
                    rec_leg_ccy = json_output.get("rec_leg_ccy")
                    if isinstance(rec_leg_ccy, str):
                        output_.rec_leg_ccy = rec_leg_ccy
                except Exception as e:
                    output_.rec_leg_ccy = str(e)

                # Receive leg payment frequency
                try:
                    rec_leg_freq_months = json_output.get("rec_leg_freq_months")
                    if isinstance(rec_leg_freq_months, int):
                        output_.rec_leg_freq_months = str(FloatUtil.to_int_or_float(rec_leg_freq_months))
                    elif rec_leg_freq_months is not None:
                        rec_leg_freq_months_entry = NumberEntry(text=str(rec_leg_freq_months))
                        rec_leg_freq_months_entry.run_generate()
                        output_.rec_leg_freq_months = str(FloatUtil.to_int_or_float(rec_leg_freq_months_entry.value))
                except Exception as e:
                    output_.rec_leg_freq_months = str(e)

                # Receive leg basis

                rec_leg_basis = json_output.get("rec_leg_basis")
                if isinstance(rec_leg_basis, str):
                    output_.rec_leg_basis = rec_leg_basis

                # Receive leg floating interest rate index
                rec_leg_float_index = json_output.get("rec_leg_float_index")
                if isinstance(rec_leg_float_index, str):
                    output_.rec_leg_float_index = rec_leg_float_index

                # Receive leg spread in basis points
                try:
                    rec_leg_float_spread_bp = json_output.get("rec_leg_float_spread_bp")
                    if isinstance(rec_leg_float_spread_bp, float):
                        output_.rec_leg_float_spread_bp = str(FloatUtil.to_int_or_float(rec_leg_float_spread_bp))
                    elif rec_leg_float_spread_bp is not None:
                        rec_leg_float_spread_bp = NumberEntry(text=str(rec_leg_float_spread_bp))
                        rec_leg_float_spread_bp.run_generate()
                        output_.rec_leg_float_spread_bp = str(FloatUtil.to_int_or_float(rec_leg_float_spread_bp.value))
                except Exception as e:
                    output_.rec_leg_float_spread_bp = str(e)

                # Receive leg fixed rate in percent
                try:
                    rec_leg_fixed_rate_pct = json_output.get("rec_leg_fixed_rate_pct")
                    if isinstance(rec_leg_fixed_rate_pct, float):
                        output_.rec_leg_fixed_rate_pct = str(FloatUtil.to_int_or_float(rec_leg_fixed_rate_pct))
                    elif rec_leg_fixed_rate_pct is not None:
                        rec_leg_fixed_rate_pct = NumberEntry(text=str(rec_leg_fixed_rate_pct))
                        rec_leg_fixed_rate_pct.run_generate()
                        output_.rec_leg_fixed_rate_pct = str(FloatUtil.to_int_or_float(rec_leg_fixed_rate_pct.value))
                except Exception as e:
                    output_.rec_leg_fixed_rate_pct = str(e)

                    
    def _compare_dicts(self, dict1, dict2):
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            raise ValueError("Both inputs must be dictionaries.")
        
        keys1 = set(dict1.keys())
        keys2 = set(dict2.keys())
        
        all_keys = keys1.union(keys2)
        differing_keys = []
        
        for key in all_keys:
            if key in dict1 and key in dict2:
                if self._get_str(dict1[key]) == self._get_str(dict2[key]):
                    print(f"Field '{key}': Matched - {dict1[key]}")
                else:
                    print(f"Field '{key}': Differ - Dict1: {dict1[key]}, Dict2: {dict2[key]}")
                    differing_keys.append(key)
            elif key in dict1:
                print(f"Field '{key}': Present only in Dict1 - {dict1[key]}")
                differing_keys.append(key)
            else:
                print(f"Field '{key}': Present only in Dict2 - {dict2[key]}")
                differing_keys.append(key)
        
        return differing_keys

    def _get_str(self, val):
        if isinstance(val, float):
            return f"{val:.8f}"
        else:
            return str(val)
        
    def _format_field_list(self, field_list: list[str], dict1: dict[Any], dict2: dict[Any]) -> str:
        formatted = ""
        for key in field_list:
            value1 = dict1.get(key, "<MISSING>")
            value2 = dict2.get(key, "<MISSING>")
            formatted += f"{key}: {value1} OR {value2}\n"
        return formatted