import sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
sys.modules["israeli_prices"]=MagicMock()
import collect as c
class TestCollector(unittest.TestCase):
 def test_city_filter(self):
  s=[NS(store_id="02",name="גבעת שאול ירושלים",city="3000",address="",sub_chain_name="יוניברס"),NS(store_id="03",name="תל אביב",city="תל אביב",address="",sub_chain_name="")]
  self.assertTrue(c.city_match(s[0],"ירושלים"))
  self.assertFalse(c.city_match(s[1],"ירושלים"))
 def test_universe_priority(self):
  s=[NS(store_id="01",name="ירושלים",city="ירושלים",address="",sub_chain_name="שופרסל דיל"),NS(store_id="02",name="ירושלים",city="ירושלים",address="",sub_chain_name="יוניברס")]
  picked,count=c.select_city_stores(s,"shufersal","ירושלים",2)
  self.assertEqual(count,2)
  self.assertEqual(picked[0].sub_chain_name,"יוניברס")
 def test_timezone(self):
  self.assertTrue(c.iso(datetime(2026,11,9,8,0)).endswith("+02:00"))
 def test_shard_code(self):
  self.assertEqual(c.shard_filename("כר"),"u05db-05e8.json.gz")
 def test_gtin_vs_internal(self):
  self.assertEqual(c.make_key(NS(gtin="0007290001234567",item_code="7290001234567"),"shufersal"),"gtin:0007290001234567")
  self.assertTrue(c.make_key(NS(gtin=None,item_code="12345"),"shufersal").startswith("internal:shufersal"))
 def test_old_store_replaced(self):
  now=datetime.now(timezone.utc)
  old={"a":{"key":"a","name":"חלב","offers":[{"storeKey":"rami-levy|0|001","sourceFetchedAt":now.isoformat()}]}}
  new={"rami-levy|0|001":[]}
  self.assertEqual(c.merge_products(old,new,now),{})
 def test_shard_roundtrip(self):
  with TemporaryDirectory() as td:
   p={"a":{"key":"a","name":"כרעיים עוף טרי","manufacturer":"","offers":[{"price":23}]}}
   self.assertGreater(c.write_shards(Path(td),p),0)
   self.assertIn("a",c.load_previous(Path(td)))
if __name__=="__main__":unittest.main()
