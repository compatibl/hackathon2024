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

import pytest
from cl.convince.context.llm_context import LlmContext
from cl.runtime.context.testing_context import TestingContext
from cl.runtime.log.exceptions.user_error import UserError
from cl.runtime.settings.preload_settings import PreloadSettings
from cl.hackathon.expected_results import ExpectedResults
from cl.hackathon.hackathon_input import HackathonInput
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_output_key import HackathonOutputKey


def test_expected_results():
    """Test ExpectedResults preload."""

    with TestingContext() as context:
        # Save records from preload directory to DB and execute run_configure on all preloaded Config records
        PreloadSettings.instance().save_and_configure()

        # Ensure there is only one ExpectedResults record
        solutions = list(context.load_all(ExpectedResults))
        if len(solutions) == 1:
            expected_results = solutions[0]
        elif len(solutions) == 0:
            raise UserError("No ExpectedResults records found, cannot proceed with scoring.")
        else:
            raise UserError(f"{len(solutions)} ExpectedResults records are found, only one should be present.")

        # Check its identifier
        if expected_results.solution_id != "ExpectedResults":
            raise UserError(f"ExpectedResults identifier is '{expected_results.solution_id}', must be 'Expected'.")

        # Get inputs and sort by trade_id
        inputs = context.load_all(HackathonInput)
        inputs = [input for input in inputs if input.trade_group == expected_results.trade_group]
        inputs = sorted(inputs, key=lambda item: item.trade_id)

        # Ensure there is an output for each input assigned to the expected solution
        for input in inputs:
            # Check if the output is present
            output_key = HackathonOutputKey(
                solution=expected_results.get_key(),
                trade_group=input.trade_group,
                trade_id=input.trade_id,
                trial_id="0",
            )
            output = context.load_one(HackathonOutput, output_key, is_record_optional=True)
            if output is None:
                raise UserError(f"Expected output record is not found for output key {output_key}")

            # Perform additional checks
            if input.entry_text.strip().lower() != output.entry_text.strip().lower():
                raise UserError(
                    f"Entry text does not match between HackathonInput and HackathonOutput records "
                    f"for trade_id='{input.trade_id}'"
                )


if __name__ == "__main__":
    pytest.main([__file__])
