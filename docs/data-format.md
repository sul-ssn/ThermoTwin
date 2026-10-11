# Формат импорта

Эталон: data/demo-network.json (генерируется scripts/export_demo.py).

Канонический JSON содержит `version` (новое неизменяемое имя), `demo`, `nodes`, `pipes`, `valves`, `consumers`, `sources`, `sensors`. Все ID уникальны во всей модели. Контура: supply / return. Координаты: [долгота, широта] WGS84.

GeoJSON: объект `FeatureCollection`, верхнее поле `properties: {"version":"import-1","demo":true}`. Каждая feature имеет `properties.entity`, одно из nodes/pipes/valves/consumers/sources/sensors. Остальные свойства совпадают с каноническим JSON. Для nodes нужна Point-геометрия; для pipes — LineString; остальные могут иметь geometry:null. Ссылки на объекты задаются ID.

- `resistance`: эффективное линейное сопротивление, бар/(м³/ч), строго положительное. Не коэффициент Дарси.
- `length_m`: м; `diameter_mm`: мм; `load_kw`: кВт; population — необязательная оценка численности.
- consumers и sources ссылаются на оба контура: supply_node / return_node.
- valve.state: open / closed / unknown. operable:false запрещает действия.
- valve.segment_id: участок, для которого арматура представляет полное отключение ребра, одна на участок.
- Импортированная модель не изменяет предыдущие расчёты.

Потерянные ссылки, несовпадение контуров, дубли ID и неверные атрибуты отклоняются (422). Повтор версии отклоняется (409). Геометрическая и реальная инженерная связность нуждаются в дополнительной верификации.
