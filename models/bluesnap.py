# -*- coding: utf-'8' "-*-"

import logging
import urllib2

from openerp import api, fields, models
from openerp.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AcquirerBlueSnap(models.Model):
    _inherit = 'payment.acquirer'

    def _get_bluesnap_urls(self, environment):
        """ BlueSnap URLS """
        if environment == 'prod':
            return {
                'bluesnap_form_url':
                'https://ws.bluesnap.com/buynow/checkout',
                'bluesnap_rest_url':
                'https://ws.bluensap.com/oauth/token',
            }
        else:
            return {
                'bluesnap_form_url':
                'https://sandbox.bluesnap.com/buynow/checkout',
                'bluesnap_rest_url':
                'https://sandbox.sandbox.bluensap.com/oauth/token',
            }

    @api.model
    def _get_providers(self):
        providers = super(AcquirerBlueSnap, self)._get_providers()
        providers.append(['bluesnap', 'BlueSnap'])
        return providers

    bluesnap_merchant_id = fields.Char(
        'BlueSnap Merchant Id',
        required_if_provider='bluesnap')

    _defaults = {
        'fees_active': False,
        'fees_dom_fixed': 0.35,
        'fees_dom_var': 3.4,
        'fees_int_fixed': 0.35,
        'fees_int_var': 3.9,
    }

    @api.multi
    def bluesnap_compute_fees(self, amount, currency_id, country_id):
        """
        Compute bluesnap fees.
        :param float amount: the amount to pay
        :param integer country_id: an ID of a res.country, or None. This is
                                   the customer's country, to be compared to
                                   the acquirer company country.
        :return float fees: computed fees
        """
        print "[%s]bluesnap_compute_fees" % __name__
        self.ensure_one()
        acquirer = self
        if not acquirer.fees_active:
            return 0.0
        country = self.env('res.country').browse(country_id)
        if country and acquirer.company_id.country_id.id == country.id:
            percentage = acquirer.fees_dom_var
            fixed = acquirer.fees_dom_fixed
        else:
            percentage = acquirer.fees_int_var
            fixed = acquirer.fees_int_fixed
        fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
        return fees

    @api.multi
    def bluesnap_form_generate_values(self, values):
        print "[%s]bluesnap_form_generate_values" % __name__
        self.ensure_one()

        acquirer = self

        if not acquirer.bluesnap_merchant_id:
            error_msg = 'YOU MUST COMPLETE acquirer.bluesnap_merchant_id'
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        if values.get("reference", "/") != "/":
            import pdb; pdb.set_trace()

        return values

    @api.multi
    def bluesnap_get_form_action_url(self):
        print "[%s]bluesnap_get_form_action_url" % __name__
        acquirer = self
        bluesnap_urls = self._get_bluesnap_urls(
            acquirer.environment)['bluesnap_form_url']
        return bluesnap_urls

    @api.model
    def bluesnap_get_merchant_order(self, merchant_order_id):
        print "[%s]bluesnap_get_merchant_order" % __name__
        self.ensure_one()
        import pdb; pdb.set_trace()
        merchant_order = None

        return merchant_order.get('response', False)

    @api.model
    def bluesnap_get_transaction_by_merchant_order(self, merchant_order_id):
        print "[%s]bluesnap_get_transaction_by_merchant_order" % __name__
        transaction = self.env['payment.transaction']

        res = transaction
        mos = []
        for acq in self.search([('provider', '=', 'bluesnap')]):
            merchant_order = acq \
                .bluesnap_get_merchant_order(merchant_order_id)

            external_reference = merchant_order.get('external_reference')
            if not external_reference:
                continue

            txs = transaction.search(
                [('reference', '=', external_reference),
                 ('acquirer_id', '=', acq.id)],
                )
            txs._merchant_order_ = merchant_order

            res = res | txs
            mos.append(merchant_order)

        return res, mos

    @api.model
    def bluesnap_get_collection(self, collection_id):
        print "[%s]bluesnap_get_collection" % __name__

        self.ensure_one()
        import pdb; pdb.set_trace()
        collection_info = None

        return collection_info.get('response', {}).get('collection', False)

    @api.model
    def bluesnap_get_transaction_by_collection(self, collection_id):
        print "[%s]bluesnap_get_transaction_by_collection" % __name__

        import pdb; pdb.set_trace()

        transaction = self.env['payment.transaction']

        res = transaction
        cos = []
        for acq in self.search([('provider', '=', 'bluesnap')]):
            collection = acq \
                .bluesnap_get_collection(collection_id)

            external_reference = collection.get('external_reference')

            if not external_reference:
                continue

            txs = transaction.search(
                [('reference', '=', external_reference),
                 ('acquirer_id', '=', acq.id)],
                )
            txs._collection_ = collection

            res = res | txs
            cos.append(collection)

        return res, cos


class TxBlueSnap(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _bluesnap_form_get_tx_from_data(self, data):
        print "[%s]_bluesnap_form_get_tx_from_data" % __name__
        reference = data.get('external_reference')

        if not reference:
            error_msg = 'BlueSnap: received data with missing reference'\
                ' (%s)' % (reference)
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        tx = self.search([('reference', '=', reference)])
        if not tx or len(tx) > 1:
            error_msg = 'BlueSnap: received data for reference %s' %\
                (reference)
            if not tx:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        return tx[0]

    @api.model
    def _bluesnap_form_get_invalid_parameters(self, tx, data):
        print "[%s]_bluesnap_form_get_invalid_parameters" % __name__
        return []

    @api.model
    def _bluesnap_form_validate(self, tx, data):
        print "[%s]_bluesnap_form_validate" % __name__
        status = data.get('collection_status') or data.get('status_detail')
        pay = tx.env['payment.method']
        data = {
            'acquirer_reference': data.get('merchant_order_id'),
            'payment_method_id': (
                pay.search([('acquirer_ref', '=', data.get('payment_type'))])
                or
                pay.create({
                    'name': data.get('payment_type'),
                    'acquirer_ref': data.get('payment_type'),
                    'partner_id':  tx.acquirer_id.company_id.partner_id.id,
                    'acquirer_id': tx.acquirer_id.id})
            ).id
        }
        if status in ['approved', 'processed', 'accredited']:
            _logger.info('Validated BlueSnap payment for tx %s: set as done'
                         % (tx.reference))
            data.update(
                state='done',
                date_validate=data.get('payment_date', fields.datetime.now())
            )
        elif status in ['pending', 'in_process', 'in_mediation']:
            _logger.info('Received notification for BlueSnap payment %s:'
                         ' set as pending' % (tx.reference))
            data.update(
                state='pending',
                state_message=data.get('pending_reason', '')
            )
        elif status in ['cancelled', 'refunded', 'charged_back', 'rejected']:
            _logger.info('Received notification for BlueSnap payment %s:'
                         ' set as cancelled' % (tx.reference))
            data.update(
                state='cancel',
                state_message=data.get('cancel_reason', '')
            )
        else:
            error = 'Received unrecognized status for BlueSnap payment %s:'\
                ' %s, set as error' % (tx.reference, status)
            _logger.info(error)
            data.update(
                state='error',
                state_message=error)
        return tx.write(data)
