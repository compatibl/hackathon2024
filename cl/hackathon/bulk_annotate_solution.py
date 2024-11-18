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

import traceback
from dataclasses import dataclass, asdict
from typing import Dict

from cl.convince.retrievers.retriever_util import RetrieverUtil
from cl.runtime import Context
from cl.runtime.experiments.trial_key import TrialKey
from cl.runtime.log.exceptions.user_error import UserError
from cl.runtime.primitive.float_util import FloatUtil
from cl.runtime.records.dataclasses_extensions import missing
from cl.convince.llms.llm import Llm
from cl.tradeentry.entries.amount_entry import AmountEntry
from cl.tradeentry.entries.currency_entry import CurrencyEntry
from cl.tradeentry.entries.date_entry import DateEntry
from cl.tradeentry.entries.date_or_tenor_entry import DateOrTenorEntry
from cl.tradeentry.entries.number_entry import NumberEntry
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_solution import HackathonSolution
from cl.hackathon.bulk_annotate_utils import find_tags, maybe_convert
from cl.tradeentry.entries.pay_freq_months_entry import PayFreqMonthsEntry
from cl.tradeentry.trades.currency_key import CurrencyKey


@dataclass(slots=True, kw_only=True)
class BulkAnnotateSolution(HackathonSolution):
    """Solution based on extracting values in one step."""

    prompt: str = missing()
    """One step prompt to parse trade."""

    @staticmethod
    def _extract_notional(extracted_notional: str | None) -> (float, str):
        notional_amount = None
        notional_currency = None
        context = Context.current()

        if extracted_notional:
            notional = AmountEntry(text=extracted_notional)
            notional.run_generate()

            if notional_amount_entry_key := notional.amount:
                notional_amount_entry = context.load_one(NumberEntry, notional_amount_entry_key)
                notional_amount_entry.run_generate()
                notional_amount = notional_amount_entry.value

            if notional_currency_entry_key := notional.currency:
                notional_currency_entry = context.load_one(CurrencyEntry, notional_currency_entry_key)

                if notional_currency_entry_currency_key := notional_currency_entry.currency:
                    notional_currency_entry_currency = context.load_one(
                        CurrencyKey, notional_currency_entry_currency_key
                    )
                    notional_currency = notional_currency_entry_currency.iso_code

        return notional_amount, notional_currency

    def _leg_entry_to_dict(self, extracted_results: Dict[str, str], trade_description: str, leg_type: str) -> Dict:
        retriever_error_message_prefix = (
            f"Error trying to extract the field from the trade description\nTrade description: {trade_description}\n"
        )

        entry_error_message_template = (
            "Error trying to process an extracted field from the trade description\n"
            "Extracted field: {extracted_field}\n"
            f"Trade description: {trade_description}\n"
            "{exception_message}"
        )

        entry_dict = {}

        # Payment Frequency
        extracted_freq_months = extracted_results.get(leg_type + "_leg_freq_months", None)
        if extracted_freq_months is not None:
            try:
                freq_months = PayFreqMonthsEntry(text=extracted_freq_months)
                freq_months.run_generate()
                entry_dict["freq_months"] = (
                    str(FloatUtil.to_int_or_float(v)) if (v := freq_months.pay_freq_months) else None
                )
            except Exception as e:
                entry_dict["freq_months"] = entry_error_message_template.format(
                    extracted_field=extracted_freq_months, exception_message=str(e)
                )

        # Floating rate index
        entry_dict["float_index"] = extracted_results.get(leg_type + "_leg_float_index", None)

        # Floating rate spread
        extracted_float_spread = extracted_results.get(leg_type + "_leg_float_spread", None)
        if extracted_float_spread is not None:
            try:
                if v:= maybe_convert(extracted_float_spread).isnumeric():
                    entry_dict["float_spread"] = v
                else:
                    float_spread = NumberEntry(text=extracted_float_spread)
                    float_spread.run_generate()
                    entry_dict["float_spread"] = str(FloatUtil.to_int_or_float(v)) if (v := float_spread.value) else None
            except Exception as e:
                entry_dict["float_spread"] = entry_error_message_template.format(
                    extracted_field=extracted_float_spread, exception_message=str(e)
                )

        # Day-count Basis
        entry_dict["basis"] = extracted_results.get(leg_type + "_leg_basis", None)

        # Notional
        extracted_notional = extracted_results.get(leg_type + "_leg_notional", None)
        notional_amount, notional_currency = self._extract_notional(extracted_notional)
        entry_dict["notional_amount"] = str(FloatUtil.to_int_or_float(v)) if (v := notional_amount) else None
        entry_dict["notional_currency"] = notional_currency

        # Currency
        extracted_currency = extracted_results.get(leg_type + "_leg_ccy", None)
        if extracted_currency is not None:
            try:
                currency = CurrencyEntry(text=extracted_currency)
                currency.run_generate()
                if notional_currency_entry_currency_key := currency.currency:
                    notional_currency_entry_currency = Context.current().load_one(
                        CurrencyKey, notional_currency_entry_currency_key
                    )
                    entry_dict["currency"] = notional_currency_entry_currency.iso_code
            except Exception as e:
                entry_dict["currency"] = entry_error_message_template.format(
                    extracted_field=extracted_currency, exception_message=str(e)
                )

        # Fixed Rate
        extracted_fixed_rate = extracted_results.get(leg_type + "_leg_fixed_rate_pct", None)
        if extracted_fixed_rate is not None:
            extracted_fixed_rate = extracted_fixed_rate.lower().replace("%", "").replace("percent", "")
            try:
                fixed_rate = NumberEntry(text=extracted_fixed_rate)
                fixed_rate.run_generate()
                entry_dict["fixed_rate"] = str(FloatUtil.to_int_or_float(v)) if (v := fixed_rate.value) else None
            except Exception as e:
                entry_dict["fixed_rate"] = entry_error_message_template.format(
                    extracted_field=extracted_fixed_rate, exception_message=str(e)
                )

        return entry_dict

    @staticmethod
    def _retrieve_trade_parameters(extracted_results, input_description: str) -> Dict:
        entry_error_message_template = (
            "Error trying to process an extracted field from the trade description\n"
            "Extracted field: {extracted_field}\n"
            f"Trade description: {input_description}\n"
            "{exception_message}"
        )

        trade_parameters = {}

        # Maturity
        extracted_maturity = extracted_results.get("maturity_date", None)
        if extracted_maturity is not None:
            try:
                maturity = DateOrTenorEntry(text=extracted_maturity)
                maturity.run_generate()
                if date := maturity.date:
                    trade_parameters["maturity_date"] = date
                else:
                    trade_parameters["tenor_years"] = (
                        str(FloatUtil.to_int_or_float(v)) if (v := maturity.years) else None
                    )
            except Exception as e:
                formatted_error_message = entry_error_message_template.format(
                    extracted_field=extracted_maturity, exception_message=str(e)
                )
                trade_parameters["maturity_date"] = formatted_error_message

        # tenor
        extracted_tenor = extracted_results.get("tenor_years", None)
        if extracted_tenor is not None:
            extracted_tenor = "".join([i for i in extracted_tenor if i.isnumeric()]) + "y"

            try:
                tenor = DateOrTenorEntry(text=extracted_tenor)
                tenor.run_generate()
                if years := tenor.years:
                    trade_parameters["tenor_years"] = str(FloatUtil.to_int_or_float(years))
            except Exception as e:
                formatted_error_message = entry_error_message_template.format(
                    extracted_field=extracted_maturity, exception_message=str(e)
                )
                trade_parameters["tenor_years"] = formatted_error_message

        # Effective date
        extracted_effective_date = extracted_results.get("effective_date", None)
        if extracted_effective_date is not None:
            try:
                effective_date = DateEntry(text=extracted_effective_date)
                effective_date.run_generate()
                if date := effective_date.date:
                    trade_parameters["effective_date"] = date
            except Exception as e:
                trade_parameters["effective_date"] = entry_error_message_template.format(
                    extracted_field=extracted_effective_date, exception_message=str(e)
                )

        return trade_parameters

    def score_output(self, output_: HackathonOutput) -> None:
        try:
            direction_prompt = """
    For the following trade entry, your task is to determine the direction one of 'Normal' or 'Reversed' 
    'Normal' means money is moving from the Client to the Bank (we/us)
    'Reversed' means money is moving from the Bank (we/us) to the Client
    
    E.g:
    Client Buys: 'Normal'
    Client Sells: 'Reversed'
    We Buy: 'Reversed'
    We Sell: 'Normal'
    Client to pay: 'Normal'
    Bank to pay: 'Reversed'
    
    Here is the trade entry:
    ```
    {trade}
    ```
    Respond in as few words as possible, end your response with either 'Normal' or 'Reversed'.
    If unsure, return 'Normal'.
    """.strip()

            if Context.current().trial is not None:
                raise UserError("Cannot override TrialId that is already set, exiting.")

            with Context(full_llm=self.llm, trial=TrialKey(trial_id=str(output_.trial_id))) as context:
                print("*" * 20 + "original" + "*" * 20)
                print(output_.entry_text)

                # Load the full LLM specified by the context
                llm = context.load_one(Llm, context.full_llm)
                query = self.prompt.format(input_text=output_.entry_text)

                # output = llm.completion(direction_prompt.format(trade=output_.entry_text))
                # direction = "reversed" not in output.lower()
                # print("*"*20 + "direction" + "*"*20)
                # print(output)
                # print(direction)
                direction = True  # directionality makes it worse

                output = llm.completion(query)

                print("*" * 20 + "tagged" + "*" * 20)
                print(output)
                # Find the substring in the original text that matches the tagged region
                # Includes error correction
                json_output = find_tags(output_.entry_text, output)
                # this format supports multiple results for each field, fix it:
                extracted_results = {k: v[0] for k, v in json_output.items()}

                if not extracted_results:
                    print("*" * 20 + "json fallback" + "*" * 20)
                    try:
                        # maybe the model returned json
                        extracted_results = RetrieverUtil.extract_json(output)
                    except:
                        pass

                print("*" * 20 + "extracted" + "*" * 20)
                print(extracted_results)
                self.build_output(output_, direction, extracted_results, {})

                found = {}
                for k, v in asdict(output_).items():
                    if k in extracted_results and v and ("error" not in v.lower()):
                        found[k] = v

                retry = {}
                for k, v in extracted_results.items():
                    if v is not None:
                        if k not in found:
                            retry[k] = maybe_convert(v)

                if retry:
                    print("*" * 20 + "retrying" + "*" * 20)
                    print(retry)
                    self.build_output(output_, direction, retry, found)

                print("*" * 20 + "done" + "*" * 20)

        except:
            traceback.print_exc()

    def build_output(self, output_, direction, extracted_results, found_dict):
        trade_parameters = self._retrieve_trade_parameters(extracted_results, output_.entry_text)
        if "maturity_date" not in found_dict:
            output_.maturity_date = trade_parameters.get("maturity_date")
        if "tenor_years" not in found_dict:
            output_.tenor_years = trade_parameters.get("tenor_years")
        if "effective_date" not in found_dict:
            output_.effective_date = trade_parameters.get("effective_date")

        if direction:
            leg_type = "pay"
        else:
            leg_type = "rec"
        # Populate pay leg
        pay_leg_parameters = self._leg_entry_to_dict(extracted_results, output_.entry_text, leg_type)

        if "pay_leg_notional" not in found_dict:
            output_.pay_leg_notional = pay_leg_parameters.get("notional_amount")
        if "pay_leg_ccy" not in found_dict:
            output_.pay_leg_ccy = pay_leg_parameters.get("notional_currency")
        if "pay_leg_basis" not in found_dict:
            output_.pay_leg_basis = pay_leg_parameters.get("basis")
        if "pay_leg_freq_months" not in found_dict:
            output_.pay_leg_freq_months = pay_leg_parameters.get("freq_months")
        if "pay_leg_float_index" not in found_dict:
            output_.pay_leg_float_index = pay_leg_parameters.get("float_index")
        if "pay_leg_float_spread_bp" not in found_dict:
            output_.pay_leg_float_spread_bp = pay_leg_parameters.get("float_spread")
        if "pay_leg_fixed_rate_pct" not in found_dict:
            output_.pay_leg_fixed_rate_pct = pay_leg_parameters.get("fixed_rate")
        if "pay_leg_ccy " not in found_dict:  # Changed key to "pay_leg_currency" for consistency
            output_.pay_leg_ccy = pay_leg_parameters.get("currency")

        if direction:
            leg_type = "rec"
        else:
            leg_type = "pay"

        # Populate receive leg
        rec_leg_parameters = self._leg_entry_to_dict(extracted_results, output_.entry_text, leg_type)
        if "rec_leg_notional" not in found_dict:
            output_.rec_leg_notional = rec_leg_parameters.get("notional_amount")
        if "rec_leg_ccy" not in found_dict:
            output_.rec_leg_ccy = rec_leg_parameters.get("notional_currency")
        if "rec_leg_basis" not in found_dict:
            output_.rec_leg_basis = rec_leg_parameters.get("basis")
        if "rec_leg_freq_months" not in found_dict:
            output_.rec_leg_freq_months = rec_leg_parameters.get("freq_months")
        if "rec_leg_float_index" not in found_dict:
            output_.rec_leg_float_index = rec_leg_parameters.get("float_index")
        if "rec_leg_float_spread_bp" not in found_dict:
            output_.rec_leg_float_spread_bp = rec_leg_parameters.get("float_spread")
        if "rec_leg_fixed_rate_pct" not in found_dict:
            output_.rec_leg_fixed_rate_pct = rec_leg_parameters.get("fixed_rate")
        if "rec_leg_ccy " not in found_dict:  # Changed key to "rec_leg_currency" for consistency
            output_.rec_leg_ccy = rec_leg_parameters.get("currency")

        # post processing:
        if "rec_leg_notional" not in found_dict:
            if output_.pay_leg_notional and not output_.rec_leg_notional:
                output_.rec_leg_notional = output_.pay_leg_notional
        if "pay_leg_notional" not in found_dict:
            if output_.rec_leg_notional and not output_.pay_leg_notional:
                output_.pay_leg_notional = output_.rec_leg_notional
