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

import copy
import dataclasses
import time
from abc import ABC
from abc import abstractmethod
from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from typing import Final
from typing import List
from typing import Tuple
from typing_extensions import Self
from cl.runtime import Context
from cl.runtime import RecordMixin
from cl.runtime import View
from cl.runtime.log.exceptions.user_error import UserError
from cl.runtime.log.log_message import LogMessage
from cl.runtime.plots.heat_map_plot import HeatMapPlot
from cl.runtime.primitive.case_util import CaseUtil
from cl.runtime.primitive.timestamp import Timestamp
from cl.runtime.records.dataclasses_extensions import missing
from cl.runtime.routers.tasks.run_response_item import handler_queue
from cl.runtime.tasks.instance_method_task import InstanceMethodTask
from cl.convince.llms.llm_key import LlmKey
from cl.convince.retrievers.annotating_retrieval import AnnotatingRetrieval
from cl.tradeentry.entries.date_entry import DateEntry
from cl.tradeentry.entries.number_entry import NumberEntry
from cl.hackathon.hackathon_input import HackathonInput
from cl.hackathon.hackathon_input_key import HackathonInputKey
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_output_key import HackathonOutputKey
from cl.hackathon.hackathon_score_item import HackathonScoreItem
from cl.hackathon.hackathon_scoring_statistics import HackathonScoringStatistics
from cl.hackathon.hackathon_solution_key import HackathonSolutionKey

COMPARE_AS_NUMBER_FIELDS: Final[Tuple] = (
    "tenor_years",
    "pay_leg_notional",
    "pay_leg_freq_months",
    "pay_leg_float_spread_bp",
    "pay_leg_fixed_rate_pct",
    "rec_leg_notional",
    "rec_leg_freq_months",
    "rec_leg_float_spread_bp",
    "rec_leg_fixed_rate_pct",
)

ERROR_KEYWORDS: Final[Tuple] = ("error", "escalation", "?")


@dataclass(slots=True, kw_only=True)
class HackathonSolution(HackathonSolutionKey, RecordMixin[HackathonSolutionKey], ABC):
    """Define parameters to convert trade entry text to the trade and perform scoring."""

    status: str | None = None
    """Current status."""

    score_pct: str | None = None
    """Score in percentage points."""

    llm: LlmKey = missing()
    """LLM that will be used to generate the output."""

    trade_group: str = missing()
    """Trade group for which scoring will be performed."""

    trade_ids: str | None = None
    """
    Dash- and comma-delimited list of trade ids to limit scoring within the group (optional).
    
    Notes:
        All trades in the group will scored if not specified
        Example: for '1-3, 5' only trades with id 1, 2, 3, 5 will be scored
    """

    trial_count: str | None = None
    """Number of trials per each input used for this scoring."""

    score: str | None = None
    """Total score for hackathon solution."""

    max_score: str | None = None
    """Maximum possible score for solution."""

    statistics: List[HackathonScoringStatistics] | None = None
    """Detailed scoring statistics for each trade across all trials."""

    inputs: List[HackathonInput] | None = None
    """The list of inputs according to the trade list."""

    outputs: List[HackathonOutput] | None = None
    """The list of calculated outputs."""

    retrievals: List[AnnotatingRetrieval] | None = None
    """The list of retrievals."""

    def get_key(self) -> HackathonSolutionKey:
        return HackathonSolutionKey(solution_id=self.solution_id)

    def init(self) -> Self:
        """Similar to __init__ but can use fields set after construction, return self to enable method chaining."""

        is_resulting_solution = "." in self.solution_id
        if not is_resulting_solution:
            if self.trial_count is None:
                self.trial_count = str(10)
        else:
            self.inputs = self.get_inputs()
            self.outputs = self.get_outputs()

        output_count = len(self.outputs) if self.outputs else None
        if output_count:
            completed_output_count = len([x for x in self.outputs if x.status == "Completed"])
            if output_count == completed_output_count:
                self.status = "Completed"
                # try:
                #     if is_resulting_solution:
                #         self.retrievals = self.view_retrievals()
                # except Exception as e:
                #     # Continue even if retrievals are not available
                #     pass

            else:
                pct_done = int(round(completed_output_count / output_count * 100, 0))
                self.status = f"{pct_done}% Done"

        # Return self to enable method chaining
        return self

    def view_inputs(self) -> List[HackathonInput]:
        """Return the list of inputs specified by the trade list."""
        return self.get_inputs()

    def view_outputs(self) -> List[HackathonOutput]:
        """Return the list of outputs (each with its score)."""
        return self.get_outputs()

    def view_statistics(self) -> List[HackathonScoringStatistics]:
        """Return the list of inputs specified by the trade list."""

        if "." in self.solution_id:
            self.calculate_statistics()
            return self.statistics
        else:
            raise UserError(
                "The statistics view is only available for scored solutions. "
                "These solutions have identifiers that end with a timestamp."
            )

    def view_retrievals(self) -> List[AnnotatingRetrieval]:
        """Return the list of used annotating retrievals."""

        if type(self).__name__ == "AnnotationSolution":  # TODO: Refactor
            context = Context.current()

            filtered_retrievals = []
            for output in self.get_outputs():
                current_retriever_id = f"{self.solution_id}::{self.trade_group}::{output.trade_id}::{output.trial_id}"
                retrievals = context.load_all(AnnotatingRetrieval)
                filtered_retrievals.extend(
                    [retrieval for retrieval in retrievals if retrieval.retriever.retriever_id == current_retriever_id]
                )

            if filtered_retrievals:
                return filtered_retrievals
            else:
                raise RuntimeError("No retrievals were generated during the scoring of this solutions.")
        else:
            raise RuntimeError("The retrievals view is only available for AnnotationSolution.")

    def get_trade_ids_list(self) -> List[int]:
        """Return the list of trade ids from the trade_ids string."""
        if not self.trade_ids:
            return []

        result = set()
        parts = self.trade_ids.split(",")

        for part in parts:
            part = part.strip()
            # Check if the part is a range like "1-3"
            if "-" in part:
                start, end = sorted([int(range_part) for range_part in part.split("-")])
                # Add the range of numbers to the result
                result.update(range(start, end + 1))
                continue

            # Add single number to the result
            result.add(int(part))

        return sorted(list(result))

    def get_inputs(self) -> List[HackathonInput]:
        """Return the list of inputs specified by the trade list."""

        # Refactor with loading by filter
        inputs = Context.current().load_all(HackathonInput)

        # Filter inputs by trade_group and trade_ids
        trade_ids_list = self.get_trade_ids_list() if self.trade_ids is not None else None
        result = [
            x
            for x in inputs
            if x.trade_group == self.trade_group and ((trade_ids_list is None) or (int(x.trade_id) in trade_ids_list))
        ]
        result = sorted(result, key=lambda x: int(x.trade_id))
        return result

    def get_outputs(self) -> List[HackathonOutput]:
        """Return the list of outputs (each with its score)."""
        outputs = Context.current().load_all(HackathonOutput)
        result = [x for x in outputs if x.solution.solution_id == self.solution_id]
        result = sorted(result, key=lambda x: int(x.trade_id))
        return result

    @abstractmethod
    def score_output(self, output_: HackathonOutput) -> None:
        """Run scoring on the output."""

    def save_trial_output(self, *, trade_id: str, trial_id: str, entry_text: str) -> None:
        """Save trial output."""
        output_ = HackathonOutput(
            solution=self.get_key(),
            trade_group=self.trade_group,
            trade_id=trade_id,
            trial_id=trial_id,
            entry_text=entry_text,
            status="Pending",
        )
        Context.current().save_one(output_)

    def score_trial_output(self, trade_id: str, trial_id: str) -> None:

        context = Context.current()
        info_msg = f"Scoring trade_id={trade_id} trial_id={trial_id} for {self.solution_id}"
        log_message = LogMessage(level="Info", message=info_msg)
        context.save_one(log_message)

        if self.is_cancelled(self.solution_id):
            raise UserError(f"Scoring for the solution {self.solution_id} has been cancelled.")

        output_key = HackathonOutputKey(
            solution=self.get_key(),
            trade_group=self.trade_group,
            trade_id=trade_id,
            trial_id=trial_id,
        )
        output_ = context.load_one(HackathonOutput, output_key)

        if output_.status == "Cancelled":
            raise UserError(f"Scoring for this output has been cancelled. Change status to Pending to rerun.")
        elif output_.status == "Completed":
            raise UserError(f"Scoring for this output has been completed. Change status to Pending to rerun.")
        elif output_.status == "Running":
            raise UserError(f"Scoring for this output is already running. Change status to Pending to rerun.")

        # Mark as running
        output_.status = "Running"
        Context.current().save_one(output_)

        # Run scoring
        self.score_output(output_)

        # Mark as completed
        output_.status = "Completed"
        Context.current().save_one(output_)

    def submit_trial_output(self, *, trade_id: str, trial_id: str) -> None:

        # Get key type based on table in request
        key_type = HackathonSolutionKey
        key_type_str = f"{key_type.__module__}.{key_type.__name__}"
        method_name = "score_trial_output"
        method_name_pascal_case = CaseUtil.snake_to_pascal_case(method_name)
        label = f"{key_type.__name__};{self.solution_id};{method_name_pascal_case}"
        handler_task = InstanceMethodTask(
            label=label,
            queue=handler_queue.get_key(),
            key_type_str=key_type_str,
            key_str=self.solution_id,
            method_name=method_name,
            method_params=[trade_id, trial_id],
        )

        # Save and submit task
        Context.current().save_one(handler_task)
        handler_queue.submit_task(handler_task)

    def run_score_one(self) -> None:
        """Perform scoring."""
        self._run_score(1)

    def run_score_all(self) -> None:
        """Perform scoring."""
        self._run_score(int(self.trial_count))

    def run_cancel_scoring(self) -> None:
        """Cancel the ongoing scoring."""
        if "." in self.solution_id:
            self.status = "Cancelled"
            Context.current().save_one(self)

    @classmethod
    def is_cancelled(cls, solution_id: str) -> bool:
        """Check if scoring has been cancelled."""
        solution = Context.current().load_one(HackathonSolution, HackathonSolutionKey(solution_id=solution_id))
        result = solution.status == "Cancelled"
        return result

    def _run_score(self, trial_count: int) -> None:
        """Perform scoring."""

        context = Context.current()
        timestamp = Timestamp.create()
        base_solution_id = self.solution_id.split(".")[0]

        # Copy solution under a new name for scoring
        scored_solution = context.load_one(type(self), self.get_key())
        scored_solution.solution_id = f"{base_solution_id}.{timestamp}"

        """Reset the score."""
        scored_solution.status = "Running"
        scored_solution.trial_count = str(trial_count)
        Context.current().save_one(scored_solution)

        # Save outputs
        for trial_index in range(trial_count):
            for input_ in self.get_inputs():
                scored_solution.save_trial_output(
                    trade_id=input_.trade_id,
                    trial_id=str(trial_index),
                    entry_text=input_.entry_text,
                )

        # Submit outputs
        for trial_index in range(trial_count):
            for input_ in self.get_inputs():
                scored_solution.submit_trial_output(trade_id=input_.trade_id, trial_id=str(trial_index))

        # Compare solution outputs with expected outputs and save HackathonScoreItems for each pair
        #scored_solution.status = "Analyzing"
        #Context.current().save_one(scored_solution)
        # scored_solution.calculate()

        # Save scoring object with total score
        scored_solution.status = "Completed"
        context.save_one(scored_solution)

    def run_analyze(self):
        # Compare solution outputs with expected outputs and save HackathonScoreItems for each pair
        self.status = "Analyzing"
        Context.current().save_one(self)
        self.calculate()

        # Save scoring object with total score
        self.status = "Completed"
        Context.current().save_one(self)

    def get_score_item(
        self, input_key: HackathonInputKey, actual_output: HackathonOutput, expected_output: HackathonOutput
    ) -> HackathonScoreItem:
        """Compare actual output with expected output and return HackathonScoreItem."""

        # Use expected output __slots__ as field names for comparison, excluding key slots
        expected_output_key_fields = expected_output.get_key().__slots__
        expected_output_fields = expected_output.__slots__

        matched_fields = []
        mismatched_fields = []
        error_fields = []

        # Iterate over expected output fields and compare values
        for field_name in [
            f for f in expected_output_fields if f not in expected_output_key_fields and f not in ("entry_text", "status")
        ]:

            expected_field_value = getattr(expected_output, field_name, None)
            actual_field_value = getattr(actual_output, field_name, None)

            # Check for error keywords
            if actual_field_value and any(keyword in actual_field_value.lower() for keyword in ERROR_KEYWORDS):
                error_fields.append(field_name)
                continue

            # Check equality for all fields
            if actual_field_value and expected_field_value:
                if "date" in field_name:
                    comparison_result = self._compare_as_dates(actual_field_value, expected_field_value)
                elif field_name in COMPARE_AS_NUMBER_FIELDS:
                    comparison_result = self._compare_as_numbers(actual_field_value, expected_field_value)
                else:
                    comparison_result = expected_field_value == actual_field_value
            else:
                comparison_result = expected_field_value == actual_field_value

            if comparison_result:
                matched_fields.append(field_name)
            else:
                mismatched_fields.append(field_name)

        # Create and return score item
        return HackathonScoreItem(
            solution=actual_output.solution,
            trade_group=actual_output.trade_group,
            trade_id=actual_output.trade_id,
            trial_id=actual_output.trial_id,
            input=input_key,
            actual_output=actual_output.get_key(),
            expected_output=expected_output.get_key(),
            matched_fields=matched_fields,
            mismatched_fields=mismatched_fields,
            error_fields=error_fields,
        )

    def calculate(self):
        """Calculate scoring info and record to self."""

        # Get solution inputs
        context = Context.current()
        inputs = self.get_inputs()

        # Set initial values of scoring fields
        details = []
        score = 0
        max_score = 0

        # Iterate over inputs, calculate scores and sum them up
        # It is assumed that all outputs exist
        for input_ in inputs:

            # Get expected output key for current input
            expected_output = input_.get_expected_output()

            # Remember input key to create score items
            input_key = input_.get_key()

            # Load outputs for current input with trial_id
            for trial_index in range(int(self.trial_count)):
                trial_id = str(trial_index)

                # Create actual output for current input and trial_index
                actual_output_key = HackathonOutputKey(
                    solution=self.get_key(),
                    trade_group=input_.trade_group,
                    trade_id=input_.trade_id,
                    trial_id=trial_id,
                )

                actual_output = context.load_one(HackathonOutput, actual_output_key)
                #while actual_output.status != "Completed":
                #    time.sleep(1)
                 #   actual_output = context.load_one(HackathonOutput, actual_output_key)

                # Create a scoring item by comparing actual and expected outputs
                score_item = self.get_score_item(input_key, actual_output, expected_output)
                Context.current().save_one(score_item)

                # Sum up scores
                score += len(score_item.matched_fields)
                score += 0.5 * len(score_item.error_fields)
                max_score += (
                    len(score_item.matched_fields) + len(score_item.mismatched_fields) + len(score_item.error_fields)
                )

                details.append(score_item.get_key())

        # Update self with calculated values
        self.score = str(score)
        self.max_score = str(max_score)
        if max_score > 0.5:
            self.score_pct = f"{round(100 * score / max_score, 2)}"

        # Calculate scoring statistics
        self.calculate_statistics()
        self.status = "Completed"
        context.save_one(self)

    @staticmethod
    def _compare_as_dates(source_date_text: str, target_date_text: str) -> bool:
        try:
            if source_date_text.strip() == target_date_text.strip():
                return True
            source_date_entry = DateEntry(text=source_date_text, locale="en-US")
            source_date_entry.run_generate()
            target_date_entry = DateEntry(text=target_date_text, locale="en-US")
            target_date_entry.run_generate()
        except Exception as e:
            Context.current().save_one(
                LogMessage(
                    level="Info",
                    message=f"An error during {source_date_text} "
                            f"vs. {target_date_text} date comparison in scoring.\n{str(e)}"
                )
            )
            # False if cannot parse as a date
            return False
        return source_date_entry.date == target_date_entry.date

    @staticmethod
    def _compare_as_numbers(source_number_text: str, target_number_text: str) -> bool:
        try:
            if source_number_text.strip() == target_number_text.strip():
                return True
            source_number_entry = NumberEntry(text=source_number_text, locale="en-US")
            source_number_entry.run_generate()
            target_number_entry = NumberEntry(text=target_number_text, locale="en-US")
            target_number_entry.run_generate()
        except Exception as e:
            Context.current().save_one(
                LogMessage(
                    level="Info",
                    message=f"An error during {source_number_text} "
                            f"vs. {target_number_text} number comparison in scoring.\n{str(e)}"
                )
            )
            # False if cannot parse as a date
            return False
        return source_number_entry.value == target_number_entry.value

    def view_heatmap(self) -> View | None:
        """Heatmap with average scores for each field and trade."""

        if "." not in self.solution_id:
            raise UserError(
                "The heatmap is only available for scored solutions. "
                "These solutions have identifiers that end with a timestamp."
            )

        context = Context.current()
        scoring_items = context.load_all(HackathonScoreItem)
        filtered_scoring_items = [item for item in scoring_items if item.solution == self.get_key()]
        if len(filtered_scoring_items) == 0:
            raise UserError("Heatmap will be generated after running Analyze.")

        first_item = filtered_scoring_items[0]
        fields = (
            (first_item.matched_fields or []) + (first_item.mismatched_fields or []) + (first_item.error_fields or [])
        )

        # Get solution inputs
        inputs = self.get_inputs()
        result_values = []

        # Group scoring items by their input key for faster lookup
        scoring_items_by_input = defaultdict(list)
        for item in filtered_scoring_items:
            scoring_items_by_input[item.input.trade_id].append(item)

        # Main loop to process each hackathon input
        for input_ in inputs:
            # Initialize the score dictionary with all fields set to 0
            score_dict = {field_name: 0 for field_name in fields}
            hackathon_input_key = input_.get_key()

            # Get all scoring items for the current input key
            scoring_items_for_input = scoring_items_by_input.get(hackathon_input_key.trade_id, [])

            # Update scores for matched fields
            for item in scoring_items_for_input:
                for matched_field in item.matched_fields:
                    score_dict[matched_field] += 1

            # Append all field scores to the result list
            result_values.extend(score_dict.values())

        # Normalize the results
        normalized_result_values = [round(result / int(self.trial_count), 2) for result in result_values]

        maximum_values = [1] * len(fields) * len(inputs)

        num_trades = len(inputs)
        num_fields = len(fields)

        row_labels = []
        for x in inputs:
            row_labels += [f"Trade {x.trade_id}"] * num_fields

        fields_labels = [CaseUtil.snake_to_title_case(file_name).replace("Leg ", "") for file_name in fields]
        col_labels = fields_labels * num_trades

        heat_map_plot = HeatMapPlot(plot_id="heat_map_plot")
        heat_map_plot.row_labels = row_labels
        heat_map_plot.col_labels = col_labels
        heat_map_plot.received_values = normalized_result_values
        heat_map_plot.expected_values = maximum_values
        heat_map_plot.x_label = "Fields"
        heat_map_plot.y_label = "Trades"

        return heat_map_plot.get_view()

    def calculate_statistics(self) -> None:
        """Generate scoring statistics for a hackathon solution."""

        # Get solution inputs
        context = Context.current()
        inputs = self.get_inputs()

        # Load all hackathon outputs
        all_outputs = context.load_all(HackathonOutput)

        # Identify fields to compare, excluding key fields and 'entry_text'
        first_output = all_outputs[0]
        expected_output_key_fields = first_output.get_key().__slots__
        expected_output_fields = first_output.__slots__
        fields_to_compare = [
            f
            for f in expected_output_fields
            if f not in expected_output_key_fields and f not in ("entry_text", "status")
        ]

        all_statistics = []
        for input_ in inputs:
            # Initialize statistics object for each input
            statistics = HackathonScoringStatistics(
                solution=self.get_key(),
                trade_group=self.trade_group,
                trade_id=input_.trade_id,
                entry_text=input_.entry_text,
            )

            # Filter outputs corresponding to the current input
            self_key = self.get_key()
            filtered_outputs = [
                output
                for output in all_outputs
                if output.solution == self_key
                and output.trade_group == input_.trade_group
                and output.trade_id == input_.trade_id
            ]

            # Get expected output key for current input
            expected_output = input_.get_expected_output()

            for field_name in fields_to_compare:
                # Gather values for the current field
                actual_field_values = [getattr(output, field_name, None) for output in filtered_outputs]
                actual_field_values = [
                    "Error" if val and val.startswith("Error") else val for val in actual_field_values
                ]

                expected_field_value = getattr(expected_output, field_name, None)

                # Generate statistics summary for the field
                field_statistics = f"{expected_field_value} =\n" + "\n".join(
                    map(lambda x: f"{x[0]} ({x[1]}/{self.trial_count})", Counter(actual_field_values).items())
                )

                # Assign the statistics to the corresponding field in the statistics object
                setattr(statistics, field_name, field_statistics)

            # Save and collect the statistics object
            context.save_one(statistics)
            all_statistics.append(statistics)

        all_statistics = sorted(all_statistics, key=lambda x: int(x.trade_id))
        self.statistics = all_statistics
