"""Regression checks for public facts observed in the Oct 19 browser pass."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    import browser_sources as browser
except ModuleNotFoundError:
    browser = None

CFG = {'stay': {'start': '2026-11-09', 'end': '2027-04-19'},
       'budget': {'target_monthly': 1200, 'max_monthly': 1400}}

class ListingEligibility(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(browser, 'The additional browser-source collectors are missing')

    def test_furnished_finder_keeps_three_month_room_as_unconfirmed(self):
        note, reason = browser.assess_listing('furnishedfinder',
            '$1,000\n/month\nUtilities: included\nMinimum stay: 3 months\nAvailable: Nov. 2, 2026\nShared Bath', CFG)
        self.assertEqual(reason, 'eligible')
        self.assertIn('$1,000', note)
        self.assertIn('confirm', note.lower())

    def test_late_start_does_not_pass_as_available_now(self):
        note, reason = browser.assess_listing('apartments',
            '$1,130\nPlus Fees\nRoom for Rent\nFurnished\n1 - 12 Month Lease , Available Jan 10, 2027', CFG)
        self.assertIsNone(note)
        self.assertEqual(reason, 'date_mismatch')

    def test_zillow_year_lease_is_excluded(self):
        note, reason = browser.assess_listing('zillow',
            '$1,300/mo\nRoom for rent\nAvailable now\n1 year lease\nNot furnished\nLease to 8/31/2027', CFG)
        self.assertIsNone(note)
        self.assertEqual(reason, 'date_mismatch')

    def test_airbnb_requires_quote_for_both_exact_dates(self):
        note, reason = browser.assess_listing('airbnb',
            '$1,377\n$1,298 monthly, originally $1,377\nCHECK-IN\n11/9/2026\nCHECKOUT\n4/19/2027\n1 guest\nReserve', CFG)
        self.assertEqual(reason, 'eligible')
        self.assertIn('$1,298', note)
        self.assertIn('exact', note.lower())
        self.assertEqual(browser.assess_listing('airbnb',
            '$1,298 monthly\nCHECK-IN\n11/15/2026\nCHECKOUT\n4/19/2027', CFG)[1], 'date_mismatch')

    def test_airbnb_search_price_without_exact_stay_quote_is_excluded(self):
        note, reason = browser.assess_listing('airbnb',
            'Add dates for prices\nCHECK-IN\n11/9/2026\nCHECKOUT\n4/19/2027', CFG)
        self.assertIsNone(note)
        self.assertEqual(reason, 'quote_unavailable')

    def test_monthly_surcharge_is_not_used_as_base_rent(self):
        self.assertEqual(browser.monthly_price('furnishedfinder',
            'Additional person adds $100/month to rent.\n$750\n/month'), 750)
        self.assertEqual(browser.monthly_price('spareroom',
            'Mandatory fee of $100/month applies.\n$1,000 monthly\n$1,150 monthly'), 1150)

    def test_missing_price_fails_closed_instead_of_empty_success(self):
        with self.assertRaises(browser.BrowserSourceError):
            browser.assess_listing('roomies', 'Please sign in to continue', CFG)

    def test_sabbatical_end_before_departure_is_excluded(self):
        self.assertEqual(browser.assess_listing('sabbaticalhomes',
            'Rates from USD $975 | Monthly\nFrom Now until March 20, 2027\nMinimum Stay\n30 Days\nUtilities are included', CFG)[1], 'date_mismatch')

    def test_known_extra_utilities_can_push_rent_over_budget(self):
        self.assertEqual(browser.assess_listing('sabbaticalhomes',
            'Rates from USD $1380 | Monthly\nFrom Now until August 30, 2027\nMinimum Stay\n3 Months\n$1,380 plus utilities ($100)', CFG)[1], 'over_budget')

    def test_spare_room_two_month_maximum_is_too_short(self):
        self.assertEqual(browser.assess_listing('spareroom',
            '$950 monthly\nAvailable\nAvailable now\nMinimum term\nNone\nMaximum term\n2 months\nFurnishings\nFurnished', CFG)[1], 'date_mismatch')

    def test_conflicting_price_stays_flagged_for_review(self):
        note, reason = browser.assess_listing('spareroom',
            'Rental: $1590 for two persons\n$1,290 monthly\nMinimum term\nNone\nMaximum term\nNone\nShort rentals considered\nFurnishings\nFurnished', CFG)
        self.assertEqual(reason, 'eligible')
        self.assertIn('conflict', note.lower())

    def test_upper_end_of_rent_range_exceeds_budget(self):
        self.assertEqual(browser.assess_listing('harvard',
            '$1,250 - $1,450 /Bedroom\nAvailable Now\n4 Month Lease', CFG)[1], 'over_budget')

    def test_craigslist_weekly_price_is_not_monthly_rent(self):
        with self.assertRaises(browser.BrowserSourceError):
            browser.assess_listing('craigslist_sublets',
                '$975 weekly\nrent period: weekly\nprivate room\nfurnished', CFG)

    def test_six_month_minimum_exceeds_requested_stay(self):
        self.assertEqual(browser.assess_listing('roomies',
            'Rent\n$1000 per month\nMinimum stay: 6 months\nAvailable on\nNow', CFG)[1], 'date_mismatch')

if __name__ == '__main__':
    unittest.main()
