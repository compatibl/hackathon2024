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
from typing import Type
from cl.runtime.records.dataclasses_extensions import missing
from cl.runtime.records.key_mixin import KeyMixin
from cl.hackathon.hackathon_input_key import HackathonInputKey
from cl.hackathon.hackathon_output_key import HackathonOutputKey
from cl.hackathon.hackathon_solution_key import HackathonSolutionKey


@dataclass(slots=True, kw_only=True)
class HackathonScoreItemKey(KeyMixin):
    """Key for class with base scoring info."""

    solution: HackathonSolutionKey = missing()
    """Related scoring."""

    trade_group: str = missing()
    """Trade group for which scoring will be performed."""

    trade_id: str = missing()
    """Unique trade identifier within the trade group."""

    trial_id: str = missing()
    """Trial identifier."""

    @classmethod
    def get_key_type(cls) -> Type:
        return HackathonScoreItemKey
