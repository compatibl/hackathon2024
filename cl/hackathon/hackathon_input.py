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
from typing import Final
from cl.runtime import RecordMixin
from cl.runtime.contexts.db_context import DbContext
from cl.runtime.records.dataclasses_extensions import required
from cl.hackathon.hackathon_input_key import HackathonInputKey
from cl.hackathon.hackathon_output import HackathonOutput
from cl.hackathon.hackathon_output_key import HackathonOutputKey
from cl.hackathon.hackathon_solution_key import HackathonSolutionKey

EXPECTED_RESULTS_SOLUTION_ID: Final[str] = "ExpectedResults"


@dataclass(slots=True, kw_only=True)
class HackathonInput(HackathonInputKey, RecordMixin[HackathonInputKey]):
    """Input text for a single hackathon trade."""

    entry_text: str = required()
    """Trade entry text for the specified trade."""

    def get_key(self) -> HackathonInputKey:
        return HackathonInputKey(trade_group=self.trade_group, trade_id=self.trade_id)

    def get_expected_output(self) -> HackathonOutput:
        expected_output_key = HackathonOutputKey(
            solution=HackathonSolutionKey(solution_id=EXPECTED_RESULTS_SOLUTION_ID),
            trade_group=self.trade_group,
            trade_id=self.trade_id,
            trial_id="0",
        )
        expected_output = DbContext.load_one(HackathonOutput, expected_output_key)
        return expected_output
