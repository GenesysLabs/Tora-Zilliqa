# -*- coding:utf-8 -*-
# Copyright 2020 Shanghai Gejing InfoTech Co.,Ltd.
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

import sys
import os
from queue import Queue
import time
import coloredlogs, logging
import json

from pyzil.zilliqa.api import ZilliqaAPI
from pyzil.crypto import zilkey
from backend.monitor.request import Request
import threading


class Monitor(threading.Thread):

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(int(os.getenv('Tora-log-level')))
        coloredlogs.install(logger=self.logger)

        threading.Thread.__init__(self)
        self.req_q = Queue()

    def run(self):
        print("run the monitor")

    def get_front_request(self):
        if not self.req_q.empty():
            return self.req_q.get()
        else:
            return None


class ZilliqaMonitor(Monitor):

    def __init__(self, url, contract_addr):
        super().__init__()
        self.api = ZilliqaAPI(url)
        self.contract_addr = contract_addr
        self.logger.info("ZilliqaMonitor Created~")

    def __resolve_event_log(self, event_log):
        params = event_log["params"]
        request_id = 0
        request_type = 0
        gas_limit = 0
        gas_price = 0
        param_data = ""
        fee = 0
        user_addr = ""
        for param in params:
            if param['vname'] == "id":
                request_id = int(param["value"])
            if param['vname'] == "from":
                user_addr = param["value"]
            if param['vname'] == "reqtype":
                request_type = int(param["value"])
                if request_type == 2:
                    param_data = self.construct_swap_param_data(params)
            if param["vname"] == "gaslimit":
                gas_limit = int(param["value"])
            if param["vname"] == "gasprice":
                gas_price = int(param["value"])
            if param["vname"] == "paramdata":
                param_data = param["value"]
            if param["vname"] == "fee":
                fee = float(param["value"])
        self.logger.info("get a new request: " + str(request_id) + " " + str(request_type) + " " + str(gas_limit) + " " + str(
            gas_price) + " " + param_data + " " + str(fee))
        return Request(request_id, request_type, param_data, gas_price, gas_limit, fee, "Zilliqa", self.contract_addr, user_addr)

    @staticmethod
    def construct_swap_param_data(params):
        param_data = {}
        for param in params:
            if param['vname'] == "swapid":
                param_data['swap_id'] = param["value"]
            if param['vname'] == "swapchain":
                param_data['swap_chain'] = param["value"]
            if param['vname'] == "txhash":
                param_data['tx_hash'] = param["value"]
            if param['vname'] == "initialaddr":
                param_data['initial_addr'] = param["value"]
            if param['vname'] == "targetaddr":
                param_data['target_addr'] = param["value"]
            if param['vname'] == "swapmoney":
                param_data['swap_money'] = param["value"]
            if param['vname'] == "id":
                param_data['verify_id'] = param["value"]
            param_data['initial_chain'] = 'Zilliqa'
        return json.dumps(param_data)

    def __get_request_from_block(self, block_num):
        txns = self.api.GetTransactionsForTxBlock(block_num)
        for txn in txns:
            if len(txn) != 0:
                receipt = self.api.GetTransaction(txn[0])["receipt"]
                if "event_logs" in receipt:
                    event_logs = receipt["event_logs"]
                    for event_log in event_logs:
                        if event_log["address"] == (zilkey.normalise_address(self.contract_addr)).lower():
                            if event_log["_eventname"] == "request" or event_log["_eventname"] == "verifyrequest":
                                self.req_q.put(self.__resolve_event_log(event_log))

    def __get_last_txn_block_num(self):
        last_txns = self.api.GetRecentTransactions()
        # self.logger.info(last_txns)
        if len(last_txns["TxnHashes"]) != 0:
            last_txn_info = self.api.GetTransaction(last_txns["TxnHashes"][0])
            return last_txn_info["receipt"]["epoch_num"]
        else:
            return "0"

    def __has_txn(self, block_num):
        block_info = self.api.GetTxBlock(block_num)
        if block_info["header"]["NumTxns"] == 0:
            return False
        else:
            return True

    def run(self):
        cur_block_num = str(int(self.api.GetCurrentMiniEpoch()) - 1)
        # cur_block_num = str(int(1031258) - 1)
        while True & (int(cur_block_num) != 0):
            if int(cur_block_num) >= int(self.api.GetCurrentMiniEpoch()):
                time.sleep(1)
            else:
                if self.__has_txn(cur_block_num):
                    self.__get_request_from_block(cur_block_num)
                    cur_block_num = str(int(cur_block_num) + 1)
                else:
                    cur_block_num = str(int(cur_block_num) + 1)
