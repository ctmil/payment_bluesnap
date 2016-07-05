# -*- coding: utf-8 -*-

import logging
import pprint
import werkzeug

from openerp import http, SUPERUSER_ID, _
from openerp.http import request
from openerp.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BlueSnapController(http.Controller):
    _notify_url = '/payment/bluesnap/ipn/'
    _return_url = '/payment/bluesnap/dpn/'
    _cancel_url = '/payment/bluesnap/cancel/'

    def _get_return_url(self, **post):
        """ Extract the return URL from the data coming from BlueSnap. """
        if post.get('collection_status') in ['approved']:
            return request.registry['ir.config_parameter'] \
                .get_param(request.cr,
                           SUPERUSER_ID,
                           'web.site.payment.approved.url', '/')
        else:
            return request.registry['ir.config_parameter'] \
                .get_param(request.cr,
                           SUPERUSER_ID,
                           'web.site.payment.cancelled.url', '/')

    def bluesnap_validate_data(self, **post):
        """ BlueSnap IPN: three steps validation to ensure data correctness

         - step 1: return an empty HTTP 200 response -> will be done at the end
           by returning ''
         - step 2: POST the complete, unaltered message back to BlueSnap (
           preceded by cmd=_notify-validate), with same encoding
         - step 3: bluesnap send either VERIFIED or INVALID (single word)

        Once data is validated, process it. """

        cr, uid, context = request.cr, request.uid, request.context
        transaction = request.registry['payment.transaction']

        reference = post.get('external_reference')
        if not reference:
            raise ValidationError(_("No local reference from BlueSnap"))

        tx_ids = transaction.search(cr, uid,
                                    [('reference', '=', reference)],
                                    context=context)
        if not tx_ids:
            raise ValidationError(
                _("No local transaction with reference %s") % reference)
        if len(tx_ids) > 1:
            raise ValidationError(
                _("Multiple transactions with reference %s") % reference)

        status = post.get('collection_status')
        if status not in ['approved', 'processed',
                          'pending', 'in_process', 'in_mediation',
                          'cancelled', 'refunded', 'charge_back', 'rejected']:
            raise ValidationError(
                _("Not valid status with reference %s") % reference)

        return transaction.form_feedback(
            cr,
            SUPERUSER_ID,
            post,
            'bluesnap',
            context=context)

    @http.route('/payment/bluesnap/ipn/', type='json', auth='none')
    def bluesnap_ipn(self, **post):
        """ BlueSnap IPN. """
        topic = request.httprequest.args.get('topic')
        tid = request.httprequest.args.get('id')

        _logger.info('Processing IPN: %s for %s' % (topic, tid))

        cr, context = request.cr, request.context
        acquirer = request.registry['payment.acquirer']

        if topic == 'merchant_order':
            # New order with transaction.
            tx, mo = acquirer.bluesnap_get_transaction_by_merchant_order(
                cr, SUPERUSER_ID, tid)
            if tx:
                _logger.info(
                    "BlueSnap: Confirm order %s for local order %s." %
                    (tid, tx.reference))
            else:
                # New order without transaction. Need create one!
                _logger.info("BlueSnap: New order %s." % tid)
        elif topic == 'payment':
            # Payment confirmation.
            tx, co = acquirer.bluesnap_get_transaction_by_collection(
                cr, SUPERUSER_ID, tid)
            if tx:
                _logger.info("BlueSnap: New payment to %s." % tid)
                tx.form_feedback(co[0], 'bluesnap')
            else:
                # New payment without transaction. Need create a payment!
                _logger.info("BlueSnap: New payment %s." % tid)
        else:
            _logger.info("BlueSnap: Unknown topic %s for %s."
                         % (topic, tid))

        return ''

    @http.route('/payment/bluesnap/dpn', type='http', auth="none")
    def bluesnap_dpn(self, **post):
        """ BlueSnap DPN """
        return_url = self._get_return_url(**post)
        self.bluesnap_validate_data(**post)
        return werkzeug.utils.redirect(return_url)

    @http.route('/payment/bluesnap/cancel', type='http', auth="none")
    def bluesnap_cancel(self, **post):
        """ When the user cancels its BlueSnap payment: GET on this route """
        _logger.info('Beginning BlueSnap cancel with post data %s',
                     pprint.pformat(post))  # debug
        return_url = self._get_return_url(**post)
        status = post.get('collection_status')
        if status == 'null':
            post['collection_status'] = 'cancelled'
        self.bluesnap_validate_data(**post)
        return werkzeug.utils.redirect(return_url)
