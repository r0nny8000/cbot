"""
This module defines Azure Functions for an HTTP-triggered function and a timer-triggered function.
It demonstrates how to handle HTTP requests and execute periodic tasks using Azure Functions.
"""

# Provides logging capabilities to track events and debug the application.
import logging
import os

import azure.functions as func  # Azure Functions Python library.
from jinja2 import Environment, FileSystemLoader
from kraken.spot import Market, User, Trade
from kraken.exceptions import *  # pylint: disable=wildcard-import,unused-wildcard-import


import cb0t.engine as engine

app = func.FunctionApp()


user = User(key=os.getenv('KRAKENAPIKEY'),
            secret=os.getenv('KRAKENAPISECRET'))
trade = Trade(key=os.getenv('KRAKENAPIKEY'),
              secret=os.getenv('KRAKENAPISECRET'))
env = os.getenv('CB0TENV', 'DEV')
env_schedule = {'DEV': '*/10 * * * * *', 'PROD': '0 0 16 */2 * *'}

# Set up the Jinja2 environment once, at the module level
template_dir = os.path.join(os.path.dirname(__file__), "cb0t/html/")
jinja_env = Environment(loader=FileSystemLoader(template_dir))


@app.route(route="ticker", auth_level="anonymous", )
def get_ticker(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP triggered function to handle requests for the Kraken ticker.
    It retrieves the ticker information from the Kraken module and returns it as a JSON response.
    """

    # Extracting the 'pair' parameter from the request.
    pair = req.params.get('pair')

    if not pair:
        return func.HttpResponse("Parameter 'pair' is required.", status_code=400)

    # If 'pair' is provided, fetch the ticker information.
    logging.info("Ticker function is processing with pair: %s", pair)

    try:

        ticker = Market().get_ticker(pair)
        assets = Market().get_asset_pairs(pair)
        logging.info('Ticker data: %s', ticker)

    except (KrakenUnknownAssetError, KrakenUnknownAssetPairError) as e:
        logging.error(str(e))
        return func.HttpResponse(str(e), status_code=500)

    # Render the HTML template with the ticker data.
    template = jinja_env.get_template("ticker.html")
    html = template.render(pair=pair, ticker=ticker, assets=assets)

    return func.HttpResponse(html, mimetype="text/html", status_code=200)


@app.route(route="balance", auth_level="anonymous")
def get_balance(req: func.HttpRequest) -> func.HttpResponse:
    """Fetches and returns the account balance from Kraken."""
    balance = user.get_account_balance()
    return func.HttpResponse(str(balance), mimetype="application/json", status_code=200)


@app.route(route="env", auth_level="anonymous")
def get_env(req: func.HttpRequest) -> func.HttpResponse:
    """Fetches and returns the environment variables."""
    return func.HttpResponse(str(env), mimetype="application/json", status_code=200)


# schedule: sec, min, hour, day, month, day_of_week


@app.timer_trigger(schedule=env_schedule[env], arg_name="timer", run_on_startup=False, use_monitor=False)
def accumulate_btc(timer: func.TimerRequest) -> None:
    """Accumulates crypto periodically."""
    if timer.past_due:
        logging.info("The timer is past due! Will continue.")

    accumulate('XXBTZEUR', 4)  # Accumulate Bitcoin in EUR
    # accumulate('XETHZEUR')  # Accumulate Ethereum in EUR
    # accumulate('SOLEUR')  # Accumulate Solana in EUR


def accumulate(pair: str, euro: float) -> None:
    """
    Accumulates a specified cryptocurrency by checking the trend and bottom conditions.
    """
    try:

        # check conditions if trend is up or bottom is reached
        if not (engine.trend_is_up(pair) or engine.bottom_is_reached(pair)):
            logging.info(
                '%s Trend and bottom conditions not met, skipping.', pair)
            return

        # optimize the amount to accumulate based on the current price
        accelerated_euro = engine.accelerate(pair, euro)
        volume = round(accelerated_euro / engine.get_asset_value(pair), 8)

        # check if minimum volume is met
        asset_pair = Market().get_asset_pairs(pair)

        ordermin = float(asset_pair[pair]['ordermin'])
        if volume < ordermin:
            logging.info('%s Volume %f is below minimum required %f, increasing volume.',
                         pair, volume, ordermin)
            volume = ordermin

        logging.info('%s Accumulating %f with %f EUR',
                     pair, volume, accelerated_euro)

        # check if environment is set to PROD
        if env != 'PROD':
            raise RuntimeError(f'Not in production environment: {env}')

        # create order
        transaction = trade.create_order(ordertype='market',
                                         pair=pair,
                                         side='buy',
                                         volume=volume)  # pylint: disable=line-too-long

        logging.info('%s Order created: %s', pair, transaction)

    except Exception as e:  # pylint: disable=broad-except
        logging.error('%s %s', pair, str(e).replace('\n', ' '))


def exit_market(pair: str) -> None:
    """
    Sets a stop loss order for a specified cryptocurrency pair.
    """
    logging.info('Setting stop loss for %s at %f', pair, 4.0)
    # Implement the logic to set a stop loss order here.
    # if trend not up, sell everything


def re_entry_market(pair: str) -> None:
    """
    Enters a position for a specified cryptocurrency pair.
    """
    logging.info('Entering position for %s', pair)
    # Implement the logic to enter a position here.
    # if trend is up, buy more
    # if bottom is reached, buy more
    # if top is reached, sell everything
