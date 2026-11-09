import sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock,patch
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

 def test_barcode_lookup_roundtrip(self):
  import gzip,json
  with TemporaryDirectory() as td:
   product={"key":"gtin:07290102397334","barcode":"7290102397334","name":"בולגרית 5%","offers":[{"price":24.7}]}
   count=c.write_barcode_shards(Path(td),{"gtin":product})
   self.assertEqual(count,1)
   path=Path(td)/"b7290102.json.gz"
   self.assertTrue(path.exists())
   with gzip.open(path,"rt",encoding="utf-8") as fh:
    self.assertEqual(json.load(fh)["products"][0]["barcode"],"7290102397334")
 def test_rotation_tries_new_branch_next_time(self):
  chain=NS(slug="rami-levy",name="רמי לוי",name_he="רמי לוי",implemented=True)
  stores=[NS(store_id=f"{i:03d}",name=f"סניף {i}",city="3000",sub_chain_id="001",sub_chain_name="רמי לוי") for i in range(1,4)]
  calls=[]
  def fake_fetch(ch,store):
   calls.append(store.store_id)
   return (f"rami-levy|001|{store.store_id}",[],{"store":store.store_id,"status":"success"})
  with TemporaryDirectory() as td,patch.object(c.ilp,"list_chains",return_value=[chain]),patch.object(c.ilp,"get_stores",return_value=NS(stores=stores)),patch.object(c,"fetch_store",side_effect=fake_fetch):
   c.collect("ירושלים",Path(td),limit=1,delay=0,restrict={"rami-levy"})
   c.collect("ירושלים",Path(td),limit=1,delay=0,restrict={"rami-levy"})
   c.collect("ירושלים",Path(td),limit=1,delay=0,restrict={"rami-levy"})
  self.assertEqual(calls,["001","002","003"])
if __name__=="__main__":unittest.main()
