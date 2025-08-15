import datetime
import logging

import numpy as np


class LinearStatePredictor:
    backlog: list[tuple[datetime.datetime, float]]

    def __init__(self, past_lookup_time: datetime.timedelta, min_val=None, max_val=None, enable_log=False, return_max=False):
        """

        :param past_lookup_time:
        :param min_val: Values are capped to this min
        :param max_val: Values are capped to this max
        """
        self.backlog = []
        self.past_time = past_lookup_time
        self.min_val = min_val
        self.max_val = max_val
        self.last_prediction = self.min_val
        self.enable_log = enable_log
        self.return_max = return_max

    def set_max_val(self,new_max):
        self.max_val = new_max

    def set_min_val(self, new_min):
        self.min_val = new_min

    def get_prediction(self)->int:
        return self.last_prediction

    def get_prediction_new_value(self, new_value: float):
        time_now = datetime.datetime.now()
        # remove too old values
        while len(self.backlog) > 0 and self.backlog[0][0] < time_now - self.past_time:
            del self.backlog[0]
        # Add new value
        self.backlog.append((time_now, new_value))

        predicted = new_value
        if len(self.backlog) > 1:
            # make a polyfit to predict next value (next= mean step ahead)
            arr = np.array(self.backlog)
            x = np.array((time_now - arr[:, 0]), dtype="timedelta64[ms]").astype(float) * -1
            y = arr[:, 1].astype(float)

            try:
                pol = np.polyfit(x, y, 1)
            except np.linalg.LinAlgError:
                return predicted # can not predict --> return current value
            mean_future = np.mean(np.diff(x))

            predicted = np.polyval(pol, mean_future)
            if self.enable_log:
                logging.info(f"new: {new_value:.1f} pred: {predicted:.1f}")
            #predicted = np.nanmean(y)
            if predicted > new_value:
                predicted = new_value
            if self.return_max:
                predicted = np.nanmax(y)
            if self.min_val is not None and predicted < self.min_val:
                predicted = self.min_val
            if self.max_val is not None and predicted > self.max_val:
                predicted = self.max_val
            
        self.last_prediction = predicted
        return predicted
