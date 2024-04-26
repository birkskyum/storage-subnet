# The MIT License (MIT)
# Copyright © 2021 Yuma Rao
# Copyright © 2023 Opentensor Foundation
# Copyright © 2024 Philantrope

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import json
import torch
import base64
import random
import bittensor as bt
from abc import ABC, abstractmethod
from typing import Any, List, Union, Dict
from storage.protocol import DeleteUser
from storage.validator.cid import generate_cid_string
from storage.validator.encryption import encrypt_data
from storage.api.utils import get_query_api_axon


class DeleteUserAPI(bt.SubnetsAPI):
    def __init__(self, wallet: "bt.wallet"):
        super().__init__(wallet)
        self.netuid = 21

    def prepare_synapse(self, cid: str, encryption_payload: Dict[str, Any]) -> DeleteUser:
        encryption_payload_json = json.dumps(encryption_payload)
        synapse = DeleteUser(data_hash=cid, encryption_payload=encryption_payload_json)
        return synapse

    def process_responses(self, responses: List[Union["bt.Synapse", Any]]) -> Union[str, List[str]]:
        success = False
        failure_modes = {"code": [], "message": []}
        for response in responses:
            if response.dendrite.status_code != 200:
                failure_modes["code"].append(response.dendrite.status_code)
                failure_modes["message"].append(response.dendrite.status_message)
                continue

            success = True

        return success