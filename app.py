from flask import Flask, redirect, render_template, request, url_for, session, flash
from utils.changelog_utils import update_cell_values_prod, update_cell_values_op
from utils.excel_utils import write_to_excel_with_formatting
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from tableau_api_lib import TableauServerConnection
from tableau_api_lib.utils import querying
from scipy.optimize import minimize

import pandas as pd
import numpy as np
import warnings
import math
import json
import os

warnings.filterwarnings("ignore")
pd.set_option("display.max_rows", None, "display.max_columns", None)
pd.options.mode.chained_assignment = None

CONFIG = json.load(open('./config/config.json'))
app = Flask(__name__)

## SQLITE DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database/capacity.db'
app.config['SQLALCHEMY_BINDS'] = {
	"two": 'sqlite:///database/base.db',
    "three": 'sqlite:///database/blue.db',
    "four": 'sqlite:///database/peakblue.db',
}

## MSSQL DATABASE
# Server = CONFIG['Con']['Server']
# Database = CONFIG['Con']['Database']
# Driver = CONFIG['Con']['Driver']
# Database_Con = f'mssql://@{Server}/{Database}?driver={Driver}'
# mssql_engine = create_engine(Database_Con)
# con = mssql_engine.connect()
# app.config['SQLALCHEMY_DATABASE_URI'] = Database_Con

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["FILE_UPLOADS"] = './static/uploaded_data/'
app.config["FILE_OUTPUT"] = './static/data/'
sqlite_engine = create_engine('sqlite:///database/capacity.db')
IS_DEV = app.env == 'development'
db = SQLAlchemy(app)
db.create_all()
db.session.commit()

## GLOBAL VARIABLES
cycle_time_reduction, backend_loading, volume_increment = 0, 40, 0 
weekly_available_hours = 0.71 * 8.5 * 2 * 6
tcr, pristine = 0.30, 0.015
weekly_available_days = 6
required_threshold = 0.95
peak_to_max = 0.91
boundary_num_op_op = (0, 100)
boundary_num_op = (0, 100)
boundary_slh = (0, 100)

optimize = False
tab_selection = 'base'
uploaded_file_name = ''
output_file_name = 'Quarterly Analysis (DATE).xlsx'
summary_demand_p2m = {}
input_check = []
demand_header = []

prod_scenario_study_ref = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Products']['Sheet_Name'])
op_scenario_study_ref = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Operations']['Sheet_Name'])
demand_df_ref = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Demand']['Sheet_Name'])

## DATABASE CLASSES & FUNCTIONS
class capacity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pbg = db.Column(db.String(200), nullable=False)
    site = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(200), nullable=False)
    operation = db.Column(db.String(200), nullable=False)
    slh = db.Column(db.String(200), nullable=False)
    slh_unit = db.Column(db.String(200), nullable=False)
    num_operation = db.Column(db.String(200), nullable=False)
    num_operator_operation = db.Column(db.String(200), nullable=False)
    takt_time = db.Column(db.String(200), nullable=False)
    weekly_capacity = db.Column(db.String(200), nullable=False)
    quarterly_capacity = db.Column(db.String(200), nullable=False)
    quarterly_capacity_frac = db.Column(db.String(200), nullable=False)
    quarterly_demand = db.Column(db.Float, nullable=False)
    p2m = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return '<p2m Summary %r>' % self.id

    def to_dict(self):
        return {
            'id': self.id,
            'pbg': self.pbg,
            'site': self.site,
            'type': self.type,
            'operation': self.operation,
            'slh': self.slh,
            'slh_unit': self.slh_unit,
            'num_operation': self.num_operation,
            'num_operator_operation': self.num_operator_operation,
            'takt_time': self.takt_time,
            'weekly_capacity': self.weekly_capacity,
            'quarterly_capacity': self.quarterly_capacity,
            'quarterly_capacity_frac': self.quarterly_capacity_frac,
            'quarterly_demand': self.quarterly_demand,
            'p2m': self.p2m
        }

class base(db.Model):
    __bind_key__ = "two"
    id = db.Column(db.Integer, primary_key=True)
    pbg = db.Column(db.String(200), nullable=False)
    site = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(200), nullable=False)
    space_op = db.Column(db.String(200), nullable=False)
    space_group = db.Column(db.String(200), nullable=False)
    op_current = db.Column(db.String(200), nullable=False)
    op_1 = db.Column(db.String(200), nullable=False)
    op_2 = db.Column(db.String(200), nullable=False)
    op_3 = db.Column(db.String(200), nullable=False)
    op_4 = db.Column(db.String(200), nullable=False)
    op_increment_1 = db.Column(db.String(200), nullable=False)
    op_increment_2 = db.Column(db.String(200), nullable=False)
    op_increment_3 = db.Column(db.String(200), nullable=False)
    op_increment_4 = db.Column(db.String(200), nullable=False)
    space_increment_1 = db.Column(db.String(200), nullable=False)
    space_increment_2 = db.Column(db.String(200), nullable=False)
    space_increment_3 = db.Column(db.String(200), nullable=False)
    space_increment_4 = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return '<base %r>' % self.id

    def to_dict(self):
        return {
        'id': self.id,
        'pbg': self.pbg,
        'site': self.site,
        'type': self.type,
        'space_group': self.space_group,
        'space_op': self.space_op,
        'op_current': self.op_current,
        'op_1': self.op_1,
        'op_2': self.op_2,
        'op_3': self.op_3,
        'op_4': self.op_4,
        'op_increment_1': self.op_increment_1,
        'op_increment_2': self.op_increment_2,
        'op_increment_3': self.op_increment_3,
        'op_increment_4': self.op_increment_4,
        'space_increment_1': self.space_increment_1,
        'space_increment_2': self.space_increment_2,
        'space_increment_3': self.space_increment_3,
        'space_increment_4': self.space_increment_4,
    }

class blue(db.Model):
    __bind_key__ = "three"
    id = db.Column(db.Integer, primary_key=True)
    pbg = db.Column(db.String(200), nullable=False)
    site = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(200), nullable=False)
    space_op = db.Column(db.String(200), nullable=False)
    space_group = db.Column(db.String(200), nullable=False)
    op_current = db.Column(db.String(200), nullable=False)
    op_1 = db.Column(db.String(200), nullable=False)
    op_2 = db.Column(db.String(200), nullable=False)
    op_3 = db.Column(db.String(200), nullable=False)
    op_4 = db.Column(db.String(200), nullable=False)
    op_increment_1 = db.Column(db.String(200), nullable=False)
    op_increment_2 = db.Column(db.String(200), nullable=False)
    op_increment_3 = db.Column(db.String(200), nullable=False)
    op_increment_4 = db.Column(db.String(200), nullable=False)
    space_increment_1 = db.Column(db.String(200), nullable=False)
    space_increment_2 = db.Column(db.String(200), nullable=False)
    space_increment_3 = db.Column(db.String(200), nullable=False)
    space_increment_4 = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return '<blue %r>' % self.id

    def to_dict(self):
        return {
        'id': self.id,
        'pbg': self.pbg,
        'site': self.site,
        'type': self.type,
        'space_group': self.space_group,
        'space_op': self.space_op,
        'op_current': self.op_current,
        'op_1': self.op_1,
        'op_2': self.op_2,
        'op_3': self.op_3,
        'op_4': self.op_4,
        'op_increment_1': self.op_increment_1,
        'op_increment_2': self.op_increment_2,
        'op_increment_3': self.op_increment_3,
        'op_increment_4': self.op_increment_4,
        'space_increment_1': self.space_increment_1,
        'space_increment_2': self.space_increment_2,
        'space_increment_3': self.space_increment_3,
        'space_increment_4': self.space_increment_4,
    }

class peakblue(db.Model):
    __bind_key__ = "four"
    id = db.Column(db.Integer, primary_key=True)
    pbg = db.Column(db.String(200), nullable=False)
    site = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(200), nullable=False)
    space_op = db.Column(db.String(200), nullable=False)
    space_group = db.Column(db.String(200), nullable=False)
    op_current = db.Column(db.String(200), nullable=False)
    op_1 = db.Column(db.String(200), nullable=False)
    op_2 = db.Column(db.String(200), nullable=False)
    op_3 = db.Column(db.String(200), nullable=False)
    op_4 = db.Column(db.String(200), nullable=False)
    op_increment_1 = db.Column(db.String(200), nullable=False)
    op_increment_2 = db.Column(db.String(200), nullable=False)
    op_increment_3 = db.Column(db.String(200), nullable=False)
    op_increment_4 = db.Column(db.String(200), nullable=False)
    space_increment_1 = db.Column(db.String(200), nullable=False)
    space_increment_2 = db.Column(db.String(200), nullable=False)
    space_increment_3 = db.Column(db.String(200), nullable=False)
    space_increment_4 = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return '<bluesky %r>' % self.id

    def to_dict(self):
        return {
        'id': self.id,
        'pbg': self.pbg,
        'site': self.site,
        'type': self.type,
        'space_group': self.space_group,
        'space_op': self.space_op,
        'op_current': self.op_current,
        'op_1': self.op_1,
        'op_2': self.op_2,
        'op_3': self.op_3,
        'op_4': self.op_4,
        'op_increment_1': self.op_increment_1,
        'op_increment_2': self.op_increment_2,
        'op_increment_3': self.op_increment_3,
        'op_increment_4': self.op_increment_4,
        'space_increment_1': self.space_increment_1,
        'space_increment_2': self.space_increment_2,
        'space_increment_3': self.space_increment_3,
        'space_increment_4': self.space_increment_4,
    }

def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier

def commit_to_db(df):
    """ commits dataframe data to database. Designed for quarterly capacity data with pre-specified columns
    :param df: data to be commited
    :type df: pd.DataFrame
    """
    db.session.query(capacity).delete()
    db.session.commit()
    headers = list(df.columns)
    df.dropna(inplace=True)
    df = df.reset_index() 
    for index in range(len(df)):
        data = capacity(pbg=df.iloc[index][headers[0]], site=df.iloc[index][headers[1]], type=df.iloc[index][headers[2]], operation=df.iloc[index][headers[3]],
        slh=df.iloc[index][headers[4]], slh_unit=df.iloc[index][headers[5]], num_operation=df.iloc[index][headers[6]], num_operator_operation=df.iloc[index][headers[7]], 
        takt_time=df.iloc[index][headers[8]], weekly_capacity=df.iloc[index][headers[9]], quarterly_capacity=df.iloc[index][headers[10]], quarterly_capacity_frac=df.iloc[index][headers[11]],
        quarterly_demand=df.iloc[index][headers[12]], p2m=df.iloc[index][headers[13]])
        db.session.add(data)
        db.session.commit()

def commit_to_db_bluesky(df, type):
    """ commits dataframe data to database. Designed for bluesky capacity data with pre-specified columns. Three seperate database
    has been created for base, blue and peakblue.
    :param df: data to be commited
    :type df: pd.DataFrame
    :param type: base, blue or peakblue
    :type type: str
    """
    if type == 'base':
        db.session.query(base).delete()
        db.session.commit()
        db.session.close()
        headers = list(df.columns)
        df = df.reset_index() 
        for index in range(len(df)):
            data = base(pbg=df.iloc[index][headers[0]], site=df.iloc[index][headers[1]], type=df.iloc[index][headers[2]], space_group=df.iloc[index][headers[3]], space_op=df.iloc[index][headers[4]],
            op_current=df.iloc[index][headers[5]], op_1=df.iloc[index][headers[6]], op_2=df.iloc[index][headers[7]], op_3=df.iloc[index][headers[8]], 
            op_4=df.iloc[index][headers[9]], op_increment_1=df.iloc[index][headers[10]], op_increment_2=df.iloc[index][headers[11]], op_increment_3=df.iloc[index][headers[12]],
            op_increment_4=df.iloc[index][headers[13]], space_increment_1=df.iloc[index][headers[14]], space_increment_2=df.iloc[index][headers[15]], space_increment_3=df.iloc[index][headers[16]],
            space_increment_4=df.iloc[index][headers[17]])
            db.session.add(data)
            db.session.commit()

    elif type == 'peakblue':
        db.session.query(peakblue).delete()
        db.session.commit()
        db.session.close()
        headers = list(df.columns)
        df = df.reset_index() 
        for index in range(len(df)):
            data = peakblue(pbg=df.iloc[index][headers[0]], site=df.iloc[index][headers[1]], type=df.iloc[index][headers[2]], space_group=df.iloc[index][headers[3]], space_op=df.iloc[index][headers[4]],
            op_current=df.iloc[index][headers[5]], op_1=df.iloc[index][headers[6]], op_2=df.iloc[index][headers[7]], op_3=df.iloc[index][headers[8]], 
            op_4=df.iloc[index][headers[9]], op_increment_1=df.iloc[index][headers[10]], op_increment_2=df.iloc[index][headers[11]], op_increment_3=df.iloc[index][headers[12]],
            op_increment_4=df.iloc[index][headers[13]], space_increment_1=df.iloc[index][headers[14]], space_increment_2=df.iloc[index][headers[15]], space_increment_3=df.iloc[index][headers[16]],
            space_increment_4=df.iloc[index][headers[17]])
            db.session.add(data)
            db.session.commit()

    else:
        db.session.query(blue).delete()
        db.session.commit()
        db.session.close()
        headers = list(df.columns)
        df = df.reset_index() 
        for index in range(len(df)):
            data = blue(pbg=df.iloc[index][headers[0]], site=df.iloc[index][headers[1]], type=df.iloc[index][headers[2]], space_group=df.iloc[index][headers[3]], space_op=df.iloc[index][headers[4]],
            op_current=df.iloc[index][headers[5]], op_1=df.iloc[index][headers[6]], op_2=df.iloc[index][headers[7]], op_3=df.iloc[index][headers[8]], 
            op_4=df.iloc[index][headers[9]], op_increment_1=df.iloc[index][headers[10]], op_increment_2=df.iloc[index][headers[11]], op_increment_3=df.iloc[index][headers[12]],
            op_increment_4=df.iloc[index][headers[13]], space_increment_1=df.iloc[index][headers[14]], space_increment_2=df.iloc[index][headers[15]], space_increment_3=df.iloc[index][headers[16]],
            space_increment_4=df.iloc[index][headers[17]])
            db.session.add(data)
            db.session.commit()

## P2M COMPUTATION FUNCTION
def compute_p2m(df, cycle_time_reduction=cycle_time_reduction, backend_loading=backend_loading, volume_increment=volume_increment, weekly_available_hours=weekly_available_hours, weekly_available_days=weekly_available_days, sort=False):
    """ computes peak two max value, based on global variables of cycle-time reduction, backend loading, volume increment and available duration.
    :param df: contains relevant operation information such as: SLH, Number Ops, Number Operator/Ops etc.
    :type df: pd.DataFrame
    :param cycle_time_reduction: factor of SLH
    :type cycle_time_reduction: float
    :param backend_loading: factor of capacity
    :type backend_loading: float
    :param volume_increment: factor of demand
    :type volume_increment: float
    :param weekly_available_hours: available duration for hourly SLH unit
    :type weekly_available_hours: float
    :param weekly_available_days: available duration for daily SLH unit
    :type weekly_available_days: float
    :param sort: to rearrange dataframe rows based on descending P2M values
    :type sort: boolean
    ...
    :return: input dataframe with computed takt time, capacity and P2M
    :rtype: pd.DataFrame
    """
    numeric_columns = ['SLH', '# Operation','# Operator/Operation', 'Quarterly Demand']
    df[numeric_columns] = df[numeric_columns].astype(float)
    
    df['SLH'] = df['SLH'] - (df['SLH'] * cycle_time_reduction/100)
    df['Takt Time'] = df['SLH'] / (df['# Operator/Operation'] * df['# Operation'])
    df['Weekly Capacity'] = np.where(df['SLH Unit'] == 'H', weekly_available_hours/df['Takt Time'], weekly_available_days/df['Takt Time'])
    df['Quarterly Capacity'] = df['Weekly Capacity'] * 5 / (backend_loading/100)
    df['Quarterly Capacity (90%)'] = df['Quarterly Capacity'] * 0.90
    df['Quarterly Demand'] = df['Quarterly Demand'] * (1 + volume_increment/100)
    df['P2M'] = (df['Quarterly Demand'] / df['Quarterly Capacity']).round(2)
    columns = list(df.columns)
    
    df[columns[:-1]] = df[columns[:-1]].round(1)
    df['Quarterly Demand'] = df['Quarterly Demand'].round(0)
    str_columns = ['SLH', '# Operation', '# Operator/Operation', 'Takt Time', 'Weekly Capacity', 'Quarterly Capacity', 'Quarterly Capacity (90%)', 'P2M', 'Quarterly Demand']
    df[str_columns] = df[str_columns].astype(str)
    demand_column = df.pop('Quarterly Demand')
    df.insert(len(columns)-2, 'Quarterly Demand', demand_column)
    if sort:
        df = df.sort_values(by='P2M', ascending=False)
    commit_to_db(df)
    return df

## OPTIMIZATION FUNCTIONS
def optimize_all(quarterly_demand, quarterly_factor, available_hours, threshold, x0, boundary1, boundary2, boundary3):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where all three input variables are checked
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [SLH, Num Ops, Num Op/Ops] to be adjusted
    :type x0: list
    :param boundary1: boundary values for SLH
    :type boundary1: tuple
    :param boundary2: boundary values for Num Ops
    :type boundary2: tuple
    :param boundary3: boundary values for Num Op/Ops
    :type boundary3: tuple
    ...
    :return: optimized variables [SLH, Num Ops, Num Op/Ops], objective value /'Optimization Failed' if solution cannot be converged/
    :rtype: list, float /str/
    """
    def objective_fcn(x):
        x1, x2, x3 = x[0], x[1], x[2] 
        return -quarterly_demand/(available_hours/(x1/(x2*x3))*quarterly_factor)

    def inequality_contraint(x):
        x1, x2, x3 = x[0], x[1], x[2] 
        return -quarterly_demand/(available_hours/(x1/(x2*x3))*quarterly_factor) + threshold

    bounds_x1 = boundary1
    bounds_x2 = boundary2
    bounds_x3 = boundary3
    bounds = (bounds_x1, bounds_x2, bounds_x3)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_slh_numop(quarterly_demand, quarterly_factor, available_hours, threshold, x0, num_op_op, boundary1, boundary2):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where two variables (demand & number operations) are checked. Number Operator/Operation is a constant.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [SLH, Num Ops] to be adjusted
    :type x0: list
    :param num_op_op: declared unadjustable variable
    :type num_op_op: float
    :param boundary1: boundary values for SLH
    :type boundary1: tuple
    :param boundary2: boundary values for Num Ops
    :type boundary2: tuple
    ...
    :return: optimized variables [SLH, Num Ops], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x1, x2 = x[0], x[1]
        return -quarterly_demand/(available_hours/(x1/(x2*num_op_op))*quarterly_factor)

    def inequality_contraint(x):
        x1, x2 = x[0], x[1]
        return -quarterly_demand/(available_hours/(x1/(x2*num_op_op))*quarterly_factor) + threshold

    bounds_x1 = boundary1
    bounds_x2 = boundary2
    bounds = (bounds_x1, bounds_x2)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_slh_numopop(quarterly_demand, quarterly_factor, available_hours, threshold, x0, num_op, boundary1, boundary3):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where two variables (demand & number operator/operations) are checked. Number Operation is a constant.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [SLH, Num Ops] to be adjusted
    :type x0: list
    :param num_op: declared unadjustable variable
    :type num_op: float
    :param boundary1: boundary values for SLH
    :type boundary1: tuple
    :param boundary2: boundary values for Num Opr/Ops
    :type boundary2: tuple
    ...
    :return: optimized variables [SLH, Num Opr/Ops], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x1, x3= x[0], x[1]
        return -quarterly_demand/(available_hours/(x1/(x3*num_op))*quarterly_factor)

    def inequality_contraint(x):
        x1, x3 = x[0], x[1]
        return -quarterly_demand/(available_hours/(x1/(x3*num_op))*quarterly_factor) + threshold

    bounds_x1 = boundary1 
    bounds_x3 = boundary3
    bounds = (bounds_x1, bounds_x3)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_numop_numopop(quarterly_demand, quarterly_factor, available_hours, threshold, x0, slh, boundary2, boundary3):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where two variables (number operation & number operator/operations) are checked. SLH is a constant.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [Num Opr/Ops, Num Ops] to be adjusted
    :type x0: list
    :param num_op: declared unadjustable variable
    :type num_op: float
    :param boundary1: boundary values for Num Ops
    :type boundary1: tuple
    :param boundary2: boundary values for Num Opr/Ops
    :type boundary2: tuple
    ...
    :return: optimized variables [Num Ops, Num Opr/Ops], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x2, x3= x[0], x[1]
        return -quarterly_demand/(available_hours/(slh/(x3*x2))*quarterly_factor)

    def inequality_contraint(x):
        x2, x3 = x[0], x[1]
        return -quarterly_demand/(available_hours/(slh/(x3*x2))*quarterly_factor) + threshold

    bounds_x2 = boundary2
    bounds_x3 = boundary3
    bounds = (bounds_x2, bounds_x3)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_slh(quarterly_demand, quarterly_factor, available_hours, threshold, x0, num_op, num_op_op, boundary1):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where one variables (SLH) is checked. Number Operation & Number Operator/Operation are constants.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [SLH] to be adjusted
    :type x0: list
    :param num_op: declared unadjustable variable
    :type num_op: float
    :param num_op_op: declared unadjustable variable
    :type num_op_op: float
    :param boundary1: boundary values for SLH
    :type boundary1: tuple
    ...
    :return: optimized variables [SLH], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x1 = x[0]
        return -quarterly_demand/(available_hours/(x1/(num_op*num_op_op))*quarterly_factor)

    def inequality_contraint(x):
        x1 = x[0]
        return -quarterly_demand/(available_hours/(x1/(num_op*num_op_op))*quarterly_factor) + threshold

    bounds_x1 = boundary1
    bounds = (bounds_x1,)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_numop(quarterly_demand, quarterly_factor, available_hours, threshold, x0, slh, num_op_op, boundary2):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where one variables (Num Operation) is checked. SLH & Number Operator/Operation are constants.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [Num Op] to be adjusted
    :type x0: list
    :param slh: declared unadjustable variable
    :type slh: float
    :param num_op_op: declared unadjustable variable
    :type num_op_op: float
    :param boundary2: boundary values for Number Operation
    :type boundary2: tuple
    ...
    :return: optimized variables [Num Op], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x2 = x[0] 
        return -quarterly_demand/(available_hours/(slh/(num_op_op*x2))*quarterly_factor)

    def inequality_contraint(x):
        x2 = x[0] 
        return -quarterly_demand/(available_hours/(slh/(num_op_op*x2))*quarterly_factor) + threshold

    bounds_x2 = boundary2
    bounds = (bounds_x2,)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def optimize_numopop(quarterly_demand, quarterly_factor, available_hours, threshold, x0, slh, num_op, boundary3):
    """ Non-linear programming to recommend paramter values based on required P2M (objective value). This function applies
    to the case where one variables (Num Operation) is checked. SLH & Number Operator/Operation are constants.
    :param quarterly_demand: input demand value
    :type quarterly_demand: float
    :param quarterly_factor: scaling factor propotionate to the backend loading factor
    :type quarterly_factor: float
    :param available_duration: hours/days
    :type available_duration: float
    :param threshold: maximum P2M value
    :type threshold: float
    :param x0: initial input variable values [Num Opr/Op] to be adjusted
    :type x0: list
    :param slh: declared unadjustable variable
    :type slh: float
    :param num_op: declared unadjustable variable
    :type num_op: float
    :param boundary3: boundary values for Number Operator/Operation
    :type boundary3: tuple
    ...
    :return: optimized variables [Num Opr/Op], objective value
    :rtype: list, float
    """
    def objective_fcn(x):
        x3= x[0]
        return -quarterly_demand/(available_hours/(slh/(x3*num_op))*quarterly_factor)

    def inequality_contraint(x):
        x3= x[0]
        return -quarterly_demand/(available_hours/(slh/(x3*num_op))*quarterly_factor) + threshold

    bounds_x3 = boundary3
    bounds = (bounds_x3,)

    constraint1 = {'type': 'ineq', 'fun': inequality_contraint}
    constraints = [constraint1]

    result = minimize(objective_fcn, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    if result.success:
        return result.x.round(1), -round(result.fun, 2)
    return 'Optimization Failed'

def get_optimized_values(x):
    quarterly_factor = 5/(backend_loading/100)
    if input_check == ['SLH', '# Operation', '# Operator/Operation']:
        x0 = [x['SLH'], x['# Operation'], x['# Operator/Operation']]
        if x['SLH Unit'] == 'H':
            return optimize_all(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, boundary1=boundary_slh, boundary2=boundary_num_op, boundary3=boundary_num_op_op)
        return optimize_all(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, boundary1=boundary_slh, boundary2=boundary_num_op, boundary3=boundary_num_op_op)

    elif input_check == ['SLH', '# Operation']:
        x0 = [x['SLH'], x['# Operation']]
        num_op_op = x['# Operator/Operation']
        if x['SLH Unit'] == 'H':
            return optimize_slh_numop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, num_op_op=num_op_op, boundary1=boundary_slh, boundary2=boundary_num_op)
        return optimize_slh_numop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, num_op_op=num_op_op, boundary1=boundary_slh, boundary2=boundary_num_op)
    
    elif input_check == ['SLH', '# Operator/Operation']:
        x0 = [x['SLH'], x['# Operator/Operation']]
        num_op = x['# Operation']
        if x['SLH Unit'] == 'H':
            return optimize_slh_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, num_op=num_op, boundary1=boundary_slh, boundary3=boundary_num_op_op)
        return optimize_slh_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, num_op=num_op, boundary1=boundary_slh, boundary3=boundary_num_op_op)
    
    elif input_check == ['# Operation', '# Operator/Operation']:
        x0 = [x['# Operation'], x['# Operator/Operation']]
        slh = x['SLH']
        if x['SLH Unit'] == 'H':
            return optimize_numop_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, slh=slh, boundary2=boundary_num_op, boundary3=boundary_num_op_op)
        return optimize_numop_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, slh=slh, boundary2=boundary_num_op, boundary3=boundary_num_op_op)
    
    elif input_check == ['SLH']:
        x0 = [x['SLH']]
        num_op, num_op_op = x['# Operation'], x['# Operator/Operation']
        if x['SLH Unit'] == 'H':
            return optimize_slh(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, num_op=num_op, num_op_op=num_op_op, boundary1=boundary_slh)
        return optimize_slh(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, num_op=num_op, num_op_op=num_op_op, boundary1=boundary_slh)
    
    elif input_check == ['# Operation']:
        x0 = [x['# Operation']]
        slh, num_op_op = x['SLH'], x['# Operator/Operation']
        if x['SLH Unit'] == 'H':
            return optimize_numop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, slh=slh, num_op_op=num_op_op, boundary2=boundary_num_op)
        return optimize_numop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, slh=slh, num_op_op=num_op_op, boundary2=boundary_num_op)

    elif input_check == ['# Operator/Operation']:
        x0 = [x['# Operator/Operation']]
        slh, num_op = x['SLH'], x['# Operation']
        if x['SLH Unit'] == 'H':
            return optimize_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_hours, threshold=required_threshold, x0=x0, slh=slh, num_op=num_op, boundary3=boundary_num_op_op)
        return optimize_numopop(x['Quarterly Demand'], quarterly_factor, available_hours=weekly_available_days, threshold=required_threshold, x0=x0, slh=slh, num_op=num_op, boundary3=boundary_num_op_op)
        
def update_datatable(df, reference_df, indexes, available_hours, available_days, backend_loading):
    """ Updates takt time, capacity and formatting due to optimization
    :param df: initial dataframe with original P2M computationss
    :type df: pd.DataFrame
    :param reference_df: truncated optimized dataframe based on maximimum input P2M value
    :type reference_df: pd.DataFrame
    :param indexes: indexes where values & formatting needs to be updated
    :type indexes: list
    :param available_hours: available duration
    :type available_hours: float
    :param available_days: available duration
    :type available_days: float
    :param backend_loading: factor of capacity
    :type backend_loading: float
    ...
    :return: updated values with required formatting
    :rtype: pd.DataFrame
    """
    for index in indexes:
        ## UPDATE TARGETED INPUT VARIABLE (FORMATTING)
        for column_header_index in range(len(input_check)):
            df.loc[index, input_check[column_header_index]] = str(df.loc[index, input_check[column_header_index]]) + ' (' + str(reference_df.loc[index,'new-values'][0][column_header_index]) + ')'

        ## UPDATE P2M VALUES (FORMATTING)
        df.loc[index,'P2M'] = str(df.loc[index,'P2M']) + ' (' + str(reference_df.loc[index,'new-values'][1]) + ')'

        ## COMPUTE NEW TAKT TIME
        if input_check == ['SLH', '# Operation', '# Operator/Operation']:
            takt_time = reference_df.loc[index,'new-values'][0][0] / ((reference_df.loc[index,'new-values'][0][1])*(reference_df.loc[index,'new-values'][0][2]))

        elif input_check == ['SLH', '# Operator/Operation']:
            takt_time = reference_df.loc[index,'new-values'][0][0] / ((reference_df.loc[index,'new-values'][0][1])*df.loc[index, '# Operation'])
    
        elif input_check == ['SLH', '# Operation']:
            takt_time = reference_df.loc[index,'new-values'][0][0] / ((reference_df.loc[index,'new-values'][0][1])*df.loc[index, '# Operator/Operation'])

        elif input_check == ['# Operation', '# Operator/Operation']:
            takt_time = df.loc[index, 'SLH'] / ((reference_df.loc[index,'new-values'][0][0])*(reference_df.loc[index,'new-values'][0][1]))
        
        elif input_check == ['SLH']:
            takt_time = reference_df.loc[index,'new-values'][0][0] / (df.loc[index, '# Operation']*df.loc[index, '# Operator/Operation'])
        
        elif input_check == ['# Operation']:
            takt_time = df.loc[index, 'SLH'] / ((reference_df.loc[index,'new-values'][0][0])*df.loc[index, '# Operator/Operation'])

        elif input_check == ['# Operator/Operation']:
            takt_time = df.loc[index, 'SLH'] / ((reference_df.loc[index,'new-values'][0][0])*df.loc[index, '# Operation'])

        ## UPDATE TAKT TIME FORMATTING
        df.loc[index,'Takt Time'] = str(df.loc[index,'Takt Time']) + ' (' + str(round(takt_time,1)) + ')'
        
        ## UPDATE WEEKLY_CAPACITY VALUE & FORMATTING
        if df.iloc[index]['SLH Unit'] == 'H':
            weekly_capacity =  available_hours / takt_time
        else:
            weekly_capacity = available_days / takt_time
        df.loc[index, 'Weekly Capacity'] = str(df.loc[index,'Weekly Capacity']) + ' (' + str(int(weekly_capacity)) + ')'

        ## UPDATE QUARTERLY_CAPACITY VALUE & FORMATTING
        quarterly_capacity = weekly_capacity * (5/(backend_loading/100))
        df.loc[index, 'Quarterly Capacity'] = str(df.loc[index, 'Quarterly Capacity']) + ' (' + str(int(quarterly_capacity)) + ')'

        ## UPDATE QUARTERLY_CAPACITY_90% VALUE & FORMATTING
        quarterly_capacity_fac = quarterly_capacity * 0.90
        df.loc[index, 'Quarterly Capacity (90%)'] = str(df.loc[index, 'Quarterly Capacity (90%)']) + ' (' + str(int(quarterly_capacity_fac)) + ')'
    return df

## BLUESKY FUNCTIONS
def bluesky_op(demand_df, prod_specs_df, production_flow_df, wc_specs_df, intermediate_df, verbose=False):
    """ Computes required operation for bluesky numbers
    :param demand_df: demand data (base, blue & peakblue)
    :type demand_df: pd.DataFrame
    :param prod_specs_df: product specifications (e.g., # Chambers, MF)
    :type prod_specs_df: pd.DataFrame
    :param prod_specs_df: product specifications (e.g., # Chambers, MF)
    :type prod_specs_df: pd.DataFrame
    :param production_flow_df: production flow (work center involved for each product)
    :type production_flow_df: pd.DataFrame
    :param wc_specs_df: work center specifications (e.g., SLH, Num Operations)
    :type wc_specs_df: pd.DataFrame
    :param verbose: show internal computations
    :type verbose: boolean
    ...
    :return: required operations for each bluesky category and for each financial year.
    :rtype: pd.DataFrame
    """
    demand_headers = demand_df.columns[1:]
    op_df = pd.DataFrame()
    op_df_intermediate = pd.DataFrame()
    for demand_header in demand_headers:
        ## GET AGGREGATED WC DEMAND
        compiled_wc_demand = compile_wc_demand(demand_df, production_flow_df, prod_specs_df, demand_header, verbose=False)
        wc_demand_dict = {
            'Operation': list(compiled_wc_demand.keys()),
            demand_header: list(compiled_wc_demand.values())
        }

        wc_demand_df = pd.DataFrame.from_dict(wc_demand_dict)
        
        wc_zero_demand = np.setdiff1d(wc_specs_df['Operation'], wc_demand_df['Operation'])
        append_df = pd.DataFrame([[op, 0] for op in wc_zero_demand], columns=['Operation', demand_header])
        wc_demand_df = pd.concat([wc_demand_df, append_df], axis=0).reset_index(drop=True)

        ## COMPUTE REQUIRED NUMBERO OF OPERATIONS TO MEET P2M

        temp = intermediate_df[['Operation', 'PBG', 'Site', 'Type', 'Space Group', '# Operator/Operation', '# Operation', 'SLH Unit', 'SLH', 'Space (Sqft)', 'Demand Multiplier', 'Time']]
        intermediate_agg_df = wc_demand_df.merge(temp[temp['Time']==demand_header[:4]], on='Operation')        
        intermediate_agg_df[demand_header] = intermediate_agg_df[demand_header] * intermediate_agg_df['Demand Multiplier']
        intermediate_agg_df[demand_header + ' Op'] = intermediate_agg_df.apply(op_computation, demand_header=demand_header, axis=1)
        intermediate_agg_df.drop_duplicates(inplace=True)
        intermediate_agg_df.reset_index(inplace=True, drop=True)
        intermediate_agg_df[demand_header + ' Op'] = intermediate_agg_df.apply(op_computation, demand_header=demand_header, axis=1)

        ## FOR INTERMEDIATE OUTPUT COMPUTATIONS
        intermediate_agg_output = intermediate_agg_df.rename(columns={demand_header: 'Op Demand', demand_header+' Op': 'Op Required'})
        intermediate_agg_output['Time'] = demand_header
        if op_df_intermediate.empty:
            op_df_intermediate = intermediate_agg_output
        else:
            op_df_intermediate = pd.concat([op_df_intermediate, intermediate_agg_output], axis=0)

        # yearly_capacity = wc_demand_df.merge(wc_specs_df, on='Operation')
        # yearly_capacity[demand_header] = yearly_capacity[demand_header] * yearly_capacity['Demand Multiplier']
        # yearly_capacity[demand_header + ' Op'] = yearly_capacity.apply(op_computation, demand_header=demand_header, axis=1)
        if verbose:
            print(demand_header)
            print(intermediate_agg_df[['Operation', demand_header]])

        ## AGGREGATE SPACE GROUPS
        df_op_changes = intermediate_agg_df.groupby('Space Group')[[demand_header + ' Op', '# Operation']].sum().reset_index()   
        # df_op_changes = yearly_capacity.groupby('Space Group')[[demand_header + ' Op', '# Operation']].sum().reset_index()   
        space_df = wc_specs_df[['PBG', 'Site', 'Type', 'Space Group', 'Space (Sqft)']].drop_duplicates().reset_index(drop=True)
        bay_space_summary = df_op_changes.merge(space_df, on='Space Group')
        bay_space_summary['Space/Op'] = bay_space_summary['Space (Sqft)'] / bay_space_summary['# Operation']
        bay_space_summary.replace([np.inf, -np.inf], 0, inplace=True)
        bay_space_summary = bay_space_summary.rename(columns={demand_header + ' Op': demand_header})

        if op_df.empty:
            op_df = bay_space_summary[['PBG', 'Site', 'Type', 'Space Group', 'Space/Op', '# Operation', demand_header]]
        else:
            op_df = pd.concat([op_df, bay_space_summary[demand_header]], axis=1)

    return op_df, op_df_intermediate

def update_dictionary(old, new):
    """ Increases existing values if key exists in the dictionary. Else, creates a new key for the value. Designed to aggregate
    demand for each operation
    :param old: exising demand values
    :type old: dict
    :param new: demand values to be added
    :type new: dict
    ...
    :return: aggregated demand values
    :rtype: dict
    """
    for key, value in new.items():
        if key in old.keys():
            old[key] += value
        else:
            old[key] = value
    return old

def compile_wc_demand(demand_df, production_flow_df, prod_specs_df, demand_header, verbose=False):
    """ used under bluesky_op function to aggregated demand for each work center
    :param demand_df: demand data (base, blue & peakblue)
    :type demand_df: pd.DataFrame
    :param prod_specs_df: product specifications (e.g., # Chambers, MF)
    :type prod_specs_df: pd.DataFrame
    :param prod_specs_df: product specifications (e.g., # Chambers, MF)
    :type prod_specs_df: pd.DataFrame
    :param production_flow_df: production flow (work center involved for each product)
    :type production_flow_df: pd.DataFrame
    :param demand_header: base, blue or peakblue
    :type demand_header: str
    :param verbose: show internal computations
    :type verbose: boolean
    ...
    :return: aggregated demand for each work center
    :rtype: dict
    """
    wc_demand = {}
    products = demand_df.Product
    for prod in products:
        prod_demand = float(demand_df[demand_header].iloc[np.where(demand_df['Product'] == prod)])
        prod_operations = production_flow_df[['Operation', 'Type']].iloc[np.where(production_flow_df['Product'] == prod)]
        prod_specs = prod_specs_df[['Type', 'Number']].iloc[np.where(prod_specs_df['Product'] == prod)]
        intermediate = prod_operations.merge(prod_specs, on=['Type'], how='left')
        intermediate['Op Demand'] = intermediate['Number']*prod_demand
        prod_wc_demand = dict(zip(intermediate['Operation'], intermediate['Op Demand']))
        update_dictionary(wc_demand, prod_wc_demand)
        if verbose:
            print(prod)
            print(wc_demand)
            print('-------------------------------------------------------------------------------------------')
    return wc_demand
    
def op_computation(x, demand_header):
    """ Computes required operation to meet 0.91 P2M
    :param x: row data
    :type x: pd.DataFrame
    :param demand_header: base, blue, peakblue
    :type demand_header: str
    ...
    :return: number operations required
    :rtype: float
    """
    demand, opr_op, std_lbr_hrs = x[demand_header], x['# Operator/Operation'], x['SLH']
    demand = demand * (1 + volume_increment/100)
    std_lbr_hrs = std_lbr_hrs - (std_lbr_hrs * cycle_time_reduction/100)
    if x['SLH Unit'] == 'H':
        duration = weekly_available_hours
    else:
        duration = weekly_available_days
    op = (demand/peak_to_max)/(duration/(std_lbr_hrs/opr_op)*(5/(backend_loading/100)))
    if op == 0:
        op = 1
    elif x['Operation'] == x['Space Group']:
        op = int(math.ceil(op))
    return round_up(op, 1)

## MPP FUNCTIONS
def create_date_range(start, end):
    """ generates a list of dates given two endpoints. 
    E.g., given 2022Q1 and 2022Q4, a list of ['2022Q1', '2022Q2', '2022Q3', '2022Q4'] is generated
    :param start: start date
    :type start: str
    :param end: end date
    :type end: str
    ...
    :rtype: required dates
    :rtype: list
    """
    date_range = [start]
    start_year, start_quarter = start.split('Q')
    end_year, end_quarter = end.split('Q')
    reference_quarter = int(start_quarter) + 1
    reference_year = int(start_year)
    while reference_year <= int(end_year):
        while reference_quarter <= 4 and not (str(reference_year) == end_year and str(reference_quarter) == end_quarter):
            date = str(reference_year) + 'Q' + str(reference_quarter)
            date_range.append(date)
            reference_quarter += 1
        reference_year += 1
        reference_quarter = 1
    date_range.append(end)
    return date_range

## QUARTERLY PAGES
@app.route("/quarterly-capacity", methods=['GET', 'POST'])
def quarterly_capacity():
    global cycle_time_reduction, backend_loading, volume_increment, weekly_available_hours, weekly_available_days, optimize, summary_demand_p2m, demand_header
    if request.method == 'POST':
        if request.form.get("export-button") == "Export":
            return redirect(request.url)

        if request.form.get("submit-button") == "Submit":
            input_hyperparams = [request.form["cycle"], request.form["backend"], request.form["volume"], request.form["hours"], request.form["days"]]
            try:
                cycle_time_reduction = float(input_hyperparams[0]) if input_hyperparams[0] else cycle_time_reduction
                backend_loading = float(input_hyperparams[1]) if input_hyperparams[1] else backend_loading
                volume_increment = float(input_hyperparams[2]) if input_hyperparams[2] else volume_increment
                weekly_available_hours = float(input_hyperparams[3]) if input_hyperparams[3] else weekly_available_hours
                weekly_available_days = float(input_hyperparams[4]) if input_hyperparams[4] else weekly_available_days
            except:
                return 'Please input a valid value. Any float values (numbers) are allowed.'
            return redirect(request.url)
        
        if request.form.get("reset-button") == "Reset":
            optimize = False
            cycle_time_reduction = 0
            backend_loading = 40
            volume_increment = 0
            weekly_available_hours = 0.71 * 8.5 * 2 * 6
            weekly_available_days = 6
            return redirect(request.url)

        if request.form.get("optimize-button") == "Optimize":
            return redirect('/modal')

    else:
        try:
            config_path = CONFIG['Excel']['Configurations']['Path']
            prod_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Product_Specs']['Sheet_Name'])
            prod_specs_df['Product'].replace({'\xa0': np.nan}, inplace=True)
            prod_specs_df['Product'] = prod_specs_df['Product'].ffill()

            wc_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Operation_Specs']['Sheet_Name'])
            wc_specs_df.columns = CONFIG['Excel']['Configurations']['Operation_Specs']['Column_Headers']
            wc_specs_df.dropna(inplace=True)

            production_flow_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Production_Flow']['Sheet_Name'])
            production_flow_df['Product'] = production_flow_df['Product'].ffill()

            demand_df = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Demand']['Sheet_Name'])
        except:
            return render_template("close_excel_error.html", route='/quarterly-capacity')

        ## UPDATE CONFIG BASED ON SCENARIO STUDY INPUT
        prod_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Products']['Sheet_Name'])
        op_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Operations']['Sheet_Name'])
        
        ## CREATE INTERMEDIATE DATAFRAME
        demands = demand_df.columns[1:]
        demand_header = demands
        intermediate_df = pd.DataFrame()
        for target_demand in demands:
            demand = demand_df[['Product', target_demand]].rename(columns={target_demand: "System_Demand"})
            intermediate = production_flow_df.merge(demand, on='Product')
            intermediate = pd.merge(intermediate, prod_specs_df[['Product','Type','Number']], on=['Product', 'Type']).rename(columns={'Number': 'Breakdown_Quantity'})
            intermediate['Component_Demand'] = intermediate['System_Demand'] * intermediate['Breakdown_Quantity']
            intermediate = intermediate.merge(wc_specs_df, on='Operation', how='outer').rename(columns={'Type_x':'Component', 'Type_y':'Type'})
            intermediate['Time'] = target_demand
            intermediate['Op_Demand'] = intermediate['Demand Multiplier'] * intermediate['Component_Demand']
            intermediate_df = pd.concat([intermediate_df, intermediate], axis=0)
        intermediate_df.reset_index(inplace=True, drop=True)


        if not prod_scenario_study.empty:
            intermediate_scenario_study_prod = prod_scenario_study.apply(update_cell_values_prod, intermediate_df=intermediate_df, prod_specs_df=prod_specs_df, demands=demands, axis=1)
            intermediate_df = intermediate_scenario_study_prod[0]
            intermediate_df['Component_Demand'] = intermediate_df['System_Demand'] * intermediate_df['Breakdown_Quantity']
            intermediate_df['Op_Demand'] = intermediate_df['Demand Multiplier'] * intermediate_df['Component_Demand']  
            
            prod_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Product_Specs']['Sheet_Name']) ## Read the Updated file
            prod_specs_df['Product'].replace({'\xa0': np.nan}, inplace=True)
            prod_specs_df['Product'] = prod_specs_df['Product'].ffill()

            prod_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Products']['Sheet_Name'])

        if not op_scenario_study.empty:
            intermediate_scenario_study_op = op_scenario_study.apply(update_cell_values_op, intermediate_df=intermediate_df, wc_specs_df=wc_specs_df, demands=demands, axis=1)
            intermediate_df = intermediate_scenario_study_op[0]

            wc_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Operation_Specs']['Sheet_Name'])
            wc_specs_df.columns = CONFIG['Excel']['Configurations']['Operation_Specs']['Column_Headers']
            wc_specs_df.dropna(inplace=True)

            op_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Operations']['Sheet_Name'])

        intermediate_df = intermediate_df[['Product', 'System_Demand', 'PBG', 'Site', 'Type', 'Operation', 'Space Group', '# Operator/Operation', '# Operation', 'SLH Unit', 'SLH', 'Space (Sqft)', 'Component', 'Breakdown_Quantity', 'Component_Demand', 'Demand Multiplier', 'Op_Demand', 'Time' ]]
        intermediate_df.rename(columns={'System_Demand': 'System Demand', 'Breakdown_Quantity': 'Breakdown Quantity', 'Component_Demand': 'Component Demand', 'Op_Demand': 'Final Demand'}, inplace=True)
        
        ## COMPUTE OP-AGGREGATED DEMAND WITH OP SPECIFICATIONS FOR ALL FY/Q
        summary_demand = {}
        for target_demand in demands:
            intermediate_fyq = intermediate_df[intermediate_df['Time'] == target_demand]
            op_agg_demand = pd.pivot_table(intermediate_fyq, values='Final Demand', index='Operation', aggfunc=np.sum)
            op_agg_demand.reset_index(inplace=True)
            op_agg_demand['Time'] = target_demand
            
            updated_wc_specs = intermediate_fyq[['PBG', 'Site', 'Type', 'Operation', 'Space Group', '# Operator/Operation', '# Operation', 'SLH Unit', 'SLH', 'Space (Sqft)']]
            updated_wc_specs = updated_wc_specs.drop_duplicates().reset_index(drop=True)
            
            operation_demand_df = op_agg_demand.merge(updated_wc_specs, on='Operation', how='outer')
            df2 = operation_demand_df[['PBG', 'Site', 'Type', 'Operation', 'SLH', 'SLH Unit', '# Operation', '# Operator/Operation', 'Final Demand']]
            df2.columns = CONFIG['Excel']['Quarterly_Capacity']['Column_Headers']
            summary_demand[target_demand] = df2

        ## LAST DEMAND FY/Q AS REFERENCE
        year_quarter = demands[-1]
        session['year_quarter'] = year_quarter
        output_path = CONFIG['Excel']['Quarterly_Capacity']['Output_Path'].replace('DATE', year_quarter) 

        if optimize:
            p2m_data_list = capacity.query.all()  # Capacity db stores output that are already optimized based on hyperparameter input
            hyperparams = (cycle_time_reduction, backend_loading, volume_increment, weekly_available_hours, weekly_available_days)
            return render_template("quarterly_capacity_datatable.html", p2m_data_list=p2m_data_list, hyperparams=hyperparams,  output_path=year_quarter)   
        else:
            summary_demand_p2m = {
                'INPUT_Demand': demand_df,
                'INPUT_Product Specs': prod_specs_df,
                'INPUT_Op Specs': wc_specs_df,
                'INPUT_Production Flow': production_flow_df,
                'Changelog (Products)': prod_scenario_study,
                'Changelog (Operations)': op_scenario_study,
                'Intermediate': intermediate_df
            }
            for year_quarter, df2 in summary_demand.items():
                p2m_df = compute_p2m(df=df2, cycle_time_reduction=cycle_time_reduction, backend_loading=backend_loading, volume_increment=volume_increment, weekly_available_hours=weekly_available_hours, weekly_available_days=weekly_available_days)
                str_columns = ['SLH', '# Operation', '# Operator/Operation', 'Takt Time', 'Weekly Capacity', 'Quarterly Capacity', 'Quarterly Capacity (90%)', 'P2M', 'Quarterly Demand']
                p2m_df[str_columns] = p2m_df[str_columns].astype(float)
                summary_demand_p2m['OUTPUT_'+year_quarter] = p2m_df

            ## OUTPUT FILE FOR DOWNLOAD
            write_to_excel_with_formatting(summary_demand_p2m, output_path)
            
            p2m_data_list = capacity.query.all()
            hyperparams = (cycle_time_reduction, backend_loading, volume_increment, weekly_available_hours, weekly_available_days)
            return render_template("quarterly_capacity_datatable.html", p2m_data_list=p2m_data_list, hyperparams=hyperparams, output_path=year_quarter)

@app.route("/modal", methods=['GET', 'POST'])
def modal():
    year_quarter = session.get('year_quarter', None)
    global required_threshold, input_check, boundary_slh, boundary_num_op, boundary_num_op_op, optimize, summary_demand_p2m, demand_header
    if request.method == 'POST':
        if request.form.get("modal-optimize-button") == "Optimize":
            optimize = True
            ## UPDATE GLOBAL VARIABLES
            required_threshold = float(request.form["threshold"]) if request.form["threshold"] else ""
            input_check = request.form.getlist('checkbox')
            boundary_slh = (float(request.form["slh_min"]) if request.form["slh_min"] else 0, float(request.form["slh_max"]) if request.form["slh_max"] else 100)
            boundary_num_op = (float(request.form["num_op_min"]) if request.form["num_op_min"] else 0, float(request.form["num_op_max"]) if request.form["num_op_max"] else 100)
            boundary_num_op_op = (float(request.form["num_op_op_min"]) if request.form["num_op_op_min"] else 0, float(request.form["num_op_op_max"]) if request.form["num_op_op_max"] else 100)

            ## READ INTERMEDIATE FILE
            for demand in demand_header:
                df = summary_demand_p2m['OUTPUT_'+demand]
                df.replace([np.inf, -np.inf], np.nan, inplace=True)
                df.dropna(how="all", inplace=True)
                df_p2m = df[df['P2M'] > required_threshold]
                df_p2m['new-values'] = df_p2m.apply(get_optimized_values, axis=1)
                indexes = df_p2m['new-values'].index 
                df = update_datatable(df, df_p2m, indexes, available_hours=weekly_available_hours, available_days=weekly_available_days, backend_loading=backend_loading)
                df = df.drop_duplicates(subset=['Operation', 'P2M'])
                df.fillna(np.inf, inplace=True)
                summary_demand_p2m['OUTPUT_'+demand] = df
            
            write_to_excel_with_formatting(summary_demand_p2m, CONFIG['Excel']['Quarterly_Capacity']['Output_Path'].replace('DATE', year_quarter) )
            commit_to_db(df)
            return redirect('/quarterly-capacity')
    return render_template("modal.html")

@app.route('/api/data')
def data():
    return {'data': [user.to_dict() for user in capacity.query]}

@app.route("/quarterly-demand")
def quarterly_demand_config():
    return render_template("quarterly_demand_config.html")

@app.route("/mpp", methods=['GET', 'POST'])
def mpp():
    if request.method == 'POST':
        if request.form.get("trawl-button") == "Trawl Tableau MPP Data":

            tableau_server_config = {
                'my_env': CONFIG['Tableau']['my_env']
            }

            conn = TableauServerConnection(tableau_server_config, env='my_env', ssl_verify=False)
            with conn.sign_in():
                print('Logged in successfully')
            
            site_views_df = querying.get_views_dataframe(conn)
            mpp_id = site_views_df[site_views_df['name'] == 'MPP_Counts'].id.iloc[0]
            df = querying.get_view_data_dataframe(conn, view_id=mpp_id)

            start= request.form["startdate"]
            end = request.form["enddate"]

            date_range = create_date_range(start, end)
            trunc_df = df.loc[df['eop_qtr'].isin(date_range)]
            trunc_df['order'] = trunc_df['CPG Module'].apply(lambda x:{'FISE':0, 'TCR':1, 'LL':2, 'Robot':3, 'MF':4}[x])

            extracted_date_range = list(trunc_df['eop_qtr'].unique())
            cpg_types = list(trunc_df['CPG Module'].unique())

            column_headers = []
            for cpg_type in cpg_types:
                for date in extracted_date_range:
                    column_headers.append(cpg_type + ' ' + date)

            mpps = CONFIG['Tableau']['mpps']
            output = pd.DataFrame(columns=column_headers)

            for mpp in mpps:
                intermediate = trunc_df[trunc_df['Product'] == mpp].sort_values(by=['order', 'eop_qtr'])
                if intermediate.empty:
                    output.loc[len(output)] = [0 for i in range(len(column_headers))]
                else:
                    # intermediate_cpg = list(intermediate['CPG Module'].unique())
                    intermediate['column_header'] = intermediate['CPG Module'] + ' ' + intermediate['eop_qtr']
                    data = dict(zip(intermediate['column_header'], intermediate['counts'].apply(lambda x: str(x.replace(',',''))).astype(int)))
                    # missing_cpg = list(set(cpg_types) - set(intermediate_cpg))
                    missing_columns = list(set(column_headers)-set(data.keys()))
                    for update in missing_columns:
                        data[update] = 0

                    output = output.append(data, ignore_index=True)

            output.index = mpps
            output.to_excel("./static/data/mpp.xlsx")

    return render_template("mpp.html") 


## BLUESKY PAGES
@app.route("/bluesky-capacity", methods=['GET', 'POST'])
def bluesky():
    ## IMPORT DEMAND
    path = CONFIG['Excel']['Bluesky']['Path']
    demand_df = pd.read_excel(path, sheet_name=CONFIG['Excel']['Bluesky']['Demand']['Sheet_Name'])
    base_header = [i for i in demand_df.columns[1:] if 'Blue' not in i]
    blue_header = [i + ' Blue' for i in base_header]
    peak_header = [i + ' Peak Blue' for i in base_header]
    # demand_df = demand_df.dropna(how='all', axis='columns')
    
    config_path = CONFIG['Excel']['Configurations']['Path']
    prod_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Product_Specs']['Sheet_Name'])
    prod_specs_df['Product'].replace({'\xa0': np.nan}, inplace=True)
    prod_specs_df['Product'] = prod_specs_df['Product'].ffill()

    wc_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Operation_Specs']['Sheet_Name'])
    wc_specs_df.columns = CONFIG['Excel']['Configurations']['Operation_Specs']['Column_Headers']
    wc_specs_df.dropna(inplace=True)

    production_flow_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Production_Flow']['Sheet_Name'])
    production_flow_df['Product'] = production_flow_df['Product'].ffill()

    ## UPDATE CONFIG BASED ON SCENARIO STUDY INPUT
    prod_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Products']['Sheet_Name'])
    op_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Operations']['Sheet_Name']) 

    ## CREATE INTERMEDIATE DATAFRAME
    intermediate_df = pd.DataFrame()
    for target_demand in base_header:
        demand = demand_df[['Product', target_demand]].rename(columns={target_demand: "System_Demand"})
        intermediate = production_flow_df.merge(demand, on='Product')
        intermediate = pd.merge(intermediate, prod_specs_df[['Product','Type','Number']], on=['Product', 'Type']).rename(columns={'Number': 'Breakdown_Quantity'})
        intermediate['Component_Demand'] = intermediate['System_Demand'] * intermediate['Breakdown_Quantity']
        intermediate = intermediate.merge(wc_specs_df, on='Operation', how='outer').rename(columns={'Type_x':'Component', 'Type_y':'Type'})
        intermediate['Time'] = target_demand
        intermediate['Op_Demand'] = intermediate['Demand Multiplier'] * intermediate['Component_Demand']
        intermediate_df = pd.concat([intermediate_df, intermediate], axis=0)
    intermediate_df.reset_index(inplace=True, drop=True)

    if not prod_scenario_study.empty:
        intermediate_scenario_study_prod = prod_scenario_study.apply(update_cell_values_prod, intermediate_df=intermediate_df, prod_specs_df=prod_specs_df, demands=base_header, axis=1)
        intermediate_df = intermediate_scenario_study_prod[0]
        intermediate_df['Component_Demand'] = intermediate_df['System_Demand'] * intermediate_df['Breakdown_Quantity']
        intermediate_df['Op_Demand'] = intermediate_df['Demand Multiplier'] * intermediate_df['Component_Demand']  
        
        prod_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Product_Specs']['Sheet_Name']) ## Read the Updated file
        prod_specs_df['Product'].replace({'\xa0': np.nan}, inplace=True)
        prod_specs_df['Product'] = prod_specs_df['Product'].ffill()

        prod_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Products']['Sheet_Name'])

    if not op_scenario_study.empty:
        intermediate_scenario_study_op = op_scenario_study.apply(update_cell_values_op, intermediate_df=intermediate_df, wc_specs_df=wc_specs_df, demands=base_header, axis=1)
        intermediate_df = intermediate_scenario_study_op[0]

        wc_specs_df = pd.read_excel(config_path, sheet_name=CONFIG['Excel']['Configurations']['Operation_Specs']['Sheet_Name'])
        wc_specs_df.columns = CONFIG['Excel']['Configurations']['Operation_Specs']['Column_Headers']
        wc_specs_df.dropna(inplace=True)

        op_scenario_study = pd.read_excel(CONFIG['Excel']['Quarterly_Capacity']['Path'], sheet_name=CONFIG['Excel']['Quarterly_Capacity']['Changelog_Operations']['Sheet_Name'])

    ## COMPUTE OP REQUIREMENTS FOR 'BASE', 'BLUE', 'PEAK BLUE' FOR ALL FY
    op_requirements_df, op_intermediate_df = bluesky_op(demand_df, prod_specs_df, production_flow_df, wc_specs_df, intermediate_df, verbose=False)

    ## OUTPUT DATA
    summary_demand_p2m = {
        'INPUT_Demand': demand_df.round(1),
        'INPUT_Product Specs': prod_specs_df,
        'INPUT_Op Specs': wc_specs_df,
        'INPUT_Production Flow': production_flow_df,
        'Changelog (Products)': prod_scenario_study,
        'Changelog (Operations)': op_scenario_study,
        'Intermediate': intermediate_df,
        'Intermediate (Computed)': op_intermediate_df
    }

    ## NARROW INTO ONE OF 'BASE', 'BLUE', 'PEAK BLUE'
    headers = [base_header, blue_header, peak_header]
    selections = ['base', 'blue', 'peakblue']
    counter = 0
    for header in headers:
        op_requirements_scenario_df = op_requirements_df[['PBG', 'Site', 'Type', 'Space Group', 'Space/Op', '# Operation'] + header]
        ## COMPUTE OP INCREMENTS
        for header_index in range(len(header)):
            if header_index == 0:
                op_requirements_scenario_df.loc[:, header[header_index] + ' Op Increment'] = op_requirements_scenario_df.loc[:, header[header_index]] - op_requirements_scenario_df.loc[:, '# Operation']
            else:
                op_requirements_scenario_df.loc[:, header[header_index] + ' Op Increment'] = op_requirements_scenario_df.loc[:, header[header_index]] - op_requirements_scenario_df.loc[:, header[header_index - 1]]

        ## COMPUTE SPACE INCREMENTS
        for header_index in range(len(header)):
            op_requirements_scenario_df.loc[:, header[header_index] + ' Space Increment'] = op_requirements_scenario_df.loc[:, header[header_index] + ' Op Increment'] * op_requirements_scenario_df.loc[:, 'Space/Op']
        
        ## COMMIT TO DB
        op_requirements_scenario_df = op_requirements_scenario_df.round(1)
        op_requirements_scenario_df[op_requirements_scenario_df.columns] = op_requirements_scenario_df[op_requirements_scenario_df.columns].astype(str)
        commit_to_db_bluesky(op_requirements_scenario_df, selections[counter])

        type_header = ['Space/Op', '# Operation'] + header + [i + ' Op Increment' for i in header] + [i + ' Space Increment' for i in header]
        op_requirements_scenario_df[type_header] = op_requirements_scenario_df[type_header].astype(float)
        summary_demand_p2m['OUTPUT_'+ selections[counter].title()] = op_requirements_scenario_df
        counter += 1

    output_path = CONFIG['Excel']['Quarterly_Capacity']['Output_Path'].replace('DATE', base_header[0] + '-' + base_header[-1]) 
    write_to_excel_with_formatting(summary_demand_p2m, output_path)

    global cycle_time_reduction, backend_loading, volume_increment, weekly_available_hours, weekly_available_days, optimize
    if request.method == 'POST':
        if request.form.get("export-button") == "Export":
            return redirect(request.url)

        if request.form.get("submit-button") == "Submit":
            input_hyperparams = [request.form["cycle"], request.form["backend"], request.form["volume"], request.form["hours"], request.form["days"]]
            try:
                cycle_time_reduction = float(input_hyperparams[0]) if input_hyperparams[0] else cycle_time_reduction
                backend_loading = float(input_hyperparams[1]) if input_hyperparams[1] else backend_loading
                volume_increment = float(input_hyperparams[2]) if input_hyperparams[2] else volume_increment
                weekly_available_hours = float(input_hyperparams[3]) if input_hyperparams[3] else weekly_available_hours
                weekly_available_days = float(input_hyperparams[4]) if input_hyperparams[4] else weekly_available_days
            except:
                return 'Please input a valid value. Any float values (numbers) are allowed.'
            return redirect(request.url)
        
        if request.form.get("reset-button") == "Reset":
            optimize = False
            cycle_time_reduction = 0
            backend_loading = 40
            volume_increment = 0
            weekly_available_hours = 0.71 * 8.5 * 2 * 6
            weekly_available_days = 6
            return redirect(request.url)

    hyperparams = (cycle_time_reduction, backend_loading, volume_increment, weekly_available_hours, weekly_available_days)
    return render_template("bluesky_capacity.html", year=base_header, hyperparams=hyperparams, output_path=base_header[0] + '-' + base_header[-1])

@app.route('/api/data-base')
def data_base():
    return {'data': [user.to_dict() for user in base.query]}

@app.route('/api/data-blue')
def data_blue():
    return {'data': [user.to_dict() for user in blue.query]}

@app.route('/api/data-peakblue')
def data_peakblue():
    return {'data': [user.to_dict() for user in peakblue.query]}
        
@app.route("/bluesky/<string:info>", methods=['GET', 'POST'])
def bluesky_info(info):
    global tab_selection
    tab_selection = json.loads(info)
    return redirect('/bluesky-capacity')

@app.route("/bluesky-demand", methods=['GET'])
def bluesky_demand():
    return render_template("bluesky_capacity_demand.html")

## HOMEPAGE
@app.route("/", methods=['GET'])
def home():
    return render_template("home.html")

## CONFIGURATION PAGES
@app.route("/changelog")
def changelog():
    return render_template("changelog.html")   

@app.route("/product-specifications", methods=['GET'])
def product_specifications():
    return render_template("product_specifications.html")

@app.route("/operation-specifications", methods=['GET'])
def operation_specifications():
    return render_template("operation_specifications.html")

@app.route("/production-flow", methods=['GET'])
def production_flow():
    return render_template("production_flow.html")

## UPLOAD PAGE (NOT IN USE)
@app.route("/upload", methods=['GET', 'POST'])
def upload():
    global uploaded_file_name
    if request.method == 'POST':
        if request.form.get("upload-button") == "Upload":
            return redirect(url_for('quarterly-capacity'))
    try:
        if os.listdir(app.config["FILE_UPLOADS"]):
            for file in os.listdir(app.config["FILE_UPLOADS"]):
                os.remove(os.path.join(app.config["FILE_UPLOADS"], file))
        file = request.files["file"]
        uploaded_file_name = file.filename
        save_location = os.path.join(app.config["FILE_UPLOADS"], file.filename)
        file.save(save_location)
        flash(f'{file.filename} has been uploaded!')
        return render_template("upload.html")
    except:
        return render_template("upload.html")

if __name__ == "__main__":
    app.secret_key = 'secret_key'
    db.create_all()
    os.environ['FLASK_ENV'] = 'development'
    app.run(debug=True)