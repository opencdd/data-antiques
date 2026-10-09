# frozen_string_literal: true

# Data repository for the East Asian Antiques 東方古董 demonstration dictionary.
# The dictionary itself (reference-docs/examples/antiques.cddal) is the
# single source; `rake browser:build` renders it into data/ as browser
# JSON with unit references bound into the IEC 62720 units dictionary.
# The gem (opencdd-ruby) is the implementation and is used read-only
# via the sibling checkout (Gemfile path dependency).

require "json"
require "fileutils"

SLUG = "antiques"
TITLE = 'East Asian Antiques 東方古董 (demonstration)'
TRANSLATIONS = ['zh-TW', 'ja', 'ko']
DATA_DIR = File.expand_path("data", __dir__)
FIXTURE = File.expand_path("reference-docs/examples/antiques.cddal", __dir__)
UNITS_JSON = File.expand_path("units.json", __dir__)

def unit_index
  @unit_index ||= begin
    units = JSON.parse(File.read(UNITS_JSON))["units"]
    idx = {}
    units.each do |u|
      [u["preferred_name"], *Array(u["synonyms"])].each do |n|
        key = n.to_s.downcase.strip.tr("_", " ")
        idx[key] ||= u["irdi"] unless key.empty?
      end
    end
    idx
  end
end

def bind_iec_units!(json_path)
  entities = JSON.parse(File.read(json_path))
  unresolved = []
  entities.each do |e|
    u = e["unit"]
    next unless u.is_a?(String) && !u.empty? && !u.include?("#")
    irdi = unit_index[u.downcase.tr("_", " ")]
    if irdi
      e["unit"] = irdi
      e["unit_text"] = u.tr("_", " ")
    else
      unresolved << "#{e["code"]}: #{u}"
    end
  end
  abort "unresolved unit references:\n  #{unresolved.join("\n  ")}" unless unresolved.empty?
  File.write(json_path, JSON.pretty_generate(entities))
end

def count_entities(database)
  {
    class: database.classes.size,
    property: database.properties.size,
    value_list: database.value_lists.size,
    value_term: database.value_terms.size,
    unit: database.units.size,
    relation: database.relations.size,
    view_control: database.view_controls.size,
  }
end

desc "Build browser JSON from the fixture"
task "browser:build" do
  require "cdd"
  db = Cdd::Cddal.parse_file(FIXTURE)
  json = Cdd::Exporters::Json.new.to_json(db)
  out_dir = File.join(DATA_DIR, SLUG)
  FileUtils.mkdir_p(out_dir)
  File.write(File.join(out_dir, "database.json"), json)
  bind_iec_units!(File.join(out_dir, "database.json"))
  registry = { "dictionaries" => [{
    "slug" => SLUG,
    "parcelId" => SLUG.upcase,
    "title" => TITLE,
    "sourceLanguage" => "en",
    "translationLanguages" => TRANSLATIONS,
    "counts" => count_entities(db),
    "metaClassIrdis" => [],
  }] }
  File.write(File.join(DATA_DIR, "index.json"), JSON.pretty_generate(registry))
  puts "Wrote #{SLUG} → #{out_dir}"
end

task default: "browser:build"

desc "Harvest Met Museum Open Access highlights and splice into the fixture"
task "browser:harvest_met" do
  sh "python3", "harvest/met_antiques.py"
  bulk = File.read("harvest/out/met_bulk.cddal")
  text = File.read(FIXTURE)
  mark_begin = "# ==== BEGIN MET MUSEUM BULK REGISTRY (generated - do not hand-edit) ===="
  mark_end = "# ==== END MET MUSEUM BULK REGISTRY ===="
  marked = /#{Regexp.escape(mark_begin)}.*?#{Regexp.escape(mark_end)}\n/m
  updated =
    if marked.match?(text)
      text.sub(marked) { bulk }
    else
      text.sub(/\z/) { "\n" + bulk }
    end
  File.write(FIXTURE, updated)
  puts "Spliced Met registry into #{FIXTURE}"
  Rake::Task["browser:build"].invoke
end
