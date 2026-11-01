# CampusNav — Báo cáo tổng hợp dự án

Ngày tổng hợp: 01-11-2026  
Thư mục dự án: `CampusNav/Campus-Navigation-codex-campus-navigation`  
Git root: `/home/qvinh/Workspace/NCKH_2027_SGU`

Tài liệu này hợp nhất các báo cáo triển khai GPS, chọn GPS bằng chuột, kiểm toán graph, graph editor, xử lý lỗi định tuyến và cập nhật hiển thị tuyến. Số liệu hiện trạng được đo lại hoặc ghi rõ là snapshot lịch sử.

## 1. Tổng quan

CampusNav dùng Python `http.server`, Leaflet/OpenStreetMap, GeoJSON, routing graph JSON và CSV access points. Hai luồng định tuyến:

- **Tòa nhà → Tòa nhà:** Dijkstra đa nguồn/đa đích qua các access point được xác nhận, cộng connector cost.
- **GPS → Tòa nhà:** chạy Nearest Edge Projection và Nearest Graph Node trên cùng input/graph snapshot; đánh giá obstacle, khả năng kết nối, connector và tổng khoảng cách rồi chọn phương án đủ điều kiện.

WGS84 `[longitude, latitude]` dùng trao đổi và hiển thị. Phép tính khoảng cách, cạnh và connector dùng mét trong local AEQD. Leaflet/OpenStreetMap không đổi CRS; không dùng pixel để tính khoảng cách.

## 2. Dữ liệu và graph hiện hành

Đo trực tiếp `data/routing/graph.json` khi tổng hợp:

| Thuộc tính | Hiện trạng |
|---|---:|
| Nodes / edges | 67 / 90 |
| Directed | false (vô hướng) |
| Trọng số | `length_m`, mét |
| Access CSV | 86 hàng; báo cáo kiểm tra ghi 35 hàng xác nhận |
| Way junction review | 51 ứng viên; 33 yes, 18 no theo snapshot audit |

Các báo cáo cũ ghi graph 75/88 ở baseline và 66/88 sau rebuild, trong khi graph hiện hành là 67/90. Git root không có tracked baseline giúp truy vết lịch sử không đầy đủ. Các số cũ là snapshot lịch sử; không được gộp hoặc hiểu là hiện trạng. Trước mọi chỉnh sửa topology cần đối chiếu graph, CSV và backup hiện hành.

### Phát hiện topology/access

- Lỗi lịch sử graph builder: các đỉnh gần như trùng chainage có thể bị gộp mà không hợp nhất identity node, gây node cô lập/junction chưa nối. Cụm đáng chú ý được audit ghi nhận ở `[106.682853, 10.759586]`.
- Không được tự nối mọi giao điểm; các hàng `no` vẫn là review-only. Graph không biểu diễn đầy đủ one-way, hàng rào, cầu vượt hoặc quyền đi bộ.
- Audit snapshot trước ghi node cô lập N006, N017, N039, N059, N063, N066; audit repair lịch sử ghi một số identity được hợp nhất. Cần kiểm tra graph hiện tại trước khi kết luận các ID này còn tồn tại.
- Endpoint geometry lệch node đến 0.86 m trong audit; sai khác chiều dài edge so với hình học tối đa 0.005 m.
- Connector/access được tính đoạn thẳng, không chứng minh có cổng hoặc lối đi thật. Hàng cần review gồm B rank1→N002, B rank2→N023, C rank4→N025 (gần/nằm trong polygon theo audit), HTA rank3 (11.46 m), sgu3 (12.05 m), sgu4 (19.94 m), sgu5 (17.66 m). `sgu1` chỉ có access `no` trong snapshot audit.
- Không chỉnh access boundary, quyết định yes/no hoặc dữ liệu ways/nodes để làm tuyến chạy qua.

### Tuyến tham chiếu lịch sử

Các tuyến dưới đây khớp Bellman–Ford độc lập trên graph snapshot; điều đó xác nhận tối ưu trên graph mã hóa, không xác nhận lối đi thực địa.

| Cặp | Trước repair (m) | Sau repair audit (m) |
|---|---:|---:|
| A → KTH | 115.47 | 105.24 |
| A → sport | 120.27 | 120.27 |
| HTA → Cantin | 146.85 | 146.85 |
| B → sgu5 | 172.00 | 170.70 |
| KLF → D | 106.46 | 106.46 |

## 3. Định tuyến GPS

### Nearest Edge Projection

GPS và từng đỉnh edge chuyển sang cùng local AEQD có đơn vị mét; tâm tính từ graph nodes. Với mỗi đoạn `(U,W)`, tính `t = clamp(((P-U)·(W-U))/||W-U||², 0, 1)`, `P' = U+t(W-U)`, rồi chọn điểm chiếu gần nhất. Từ chối snap quá ngưỡng, chèn virtual node vào adjacency tạm, tách trọng số theo tỷ lệ dọc edge và chạy Dijkstra tới các destination access nodes. Graph file không bị sửa; hai đoạn mới bảo toàn tổng trọng số cạnh.

### Nearest Graph Node và đánh giá

Virtual source nằm tại GPS. Ứng viên graph node nằm trong 50 m; connector tính bằng mét và bị loại nếu cắt polygon building đã biết. Chỉ tạo cạnh trong graph tạm. Khi dữ liệu không xác nhận lối đi, trạng thái là `UNVERIFIED`, không suy diễn thành đường đi bộ.

Ngưỡng cấu hình: `MAX_GPS_ACCURACY_METERS = 50 m`, `MAX_SNAP_DISTANCE_METERS = 50 m`, `MAX_NODE_CONNECTOR_DISTANCE_METERS = 50 m`. Đây là ngưỡng cấu hình ban đầu, chưa hiệu chỉnh thực địa. Accuracy trình duyệt kém bị từ chối; GPS mô phỏng gửi `accuracy: null`/`location_source: map`, không giả lập độ chính xác.

## 4. Giao diện Leaflet

- Chế độ building-to-building và GPS-to-building độc lập.
- GPS thực tế dùng Geolocation API; GPS mô phỏng được chọn bằng click bản đồ. `mousemove` hiển thị lat/lon 7 chữ số thập phân.
- Marker, projection, snap connector, candidate routes và selected route có layer riêng trong Layer Control.
- Thay đổi GPS/đích/chế độ dọn route cũ; request version ngăn response cũ ghi đè kết quả mới.
- Đã sửa lỗi xóa `#status` sau 6 giây gây TypeError trước khi gửi request.
- Candidate có `INVALID` validation không được vẽ; bảng nêu lý do.

### Nét tuyến trùng nhau — cập nhật hiện tại

Candidate Nearest Edge vàng được vẽ trước với nét rộng 10 px. Selected route đỏ vẽ phía trên bằng nét đứt 4 px. Khi cùng hình học, hai mép vàng và khe nét đứt vẫn lộ ra để phân biệt; không dịch tọa độ tuyến, không thay đổi chiều dài hay thuật toán. Nearest Node giữ màu xanh đậm và dash riêng. Candidate `INVALID` vẫn bị ẩn.

## 5. API và graph editor

API định tuyến được giữ: `POST /api/route/from-gps`, `POST /api/route/between-places`, `POST /api/route/evaluate-gps`. Các endpoint bổ sung: `GET /api/graph`, `POST /api/graph/edits`, `GET /api/audit/access-points`.

Graph editor hỗ trợ Move/Add/Split/Connect/Delete, Undo/Reset/Save trên draft. Backend kiểm tra revision, tọa độ, node/edge refs, trọng số mét, backup graph và `graph_nodes.csv` trước khi cập nhật, đồng thời ghi `graph_edit_log.jsonl`. Không tự merge node hay nối giao điểm. Access CSV/review decisions không được editor cập nhật. Báo cáo trước ghi save/backup/restore được test trên thư mục tạm; chưa xác nhận Save lên production graph.

## 6. Nguyên nhân lỗi định tuyến đã xử lý

1. Polygon validator cũ coi boundary contact như interior và dùng epsilon không đúng đơn vị cho đoạn WGS84 nhỏ. Đã chia connector tại giao điểm polygon boundary rồi kiểm tra khoảng có độ dài dương trong polygon; vẫn chặn connector đi vào building.
2. Giao diện xóa `#status` sau 6 giây. Nút tìm đường sau đó lỗi trước fetch, còn tuyến preview cũ tạo cảm giác Dijkstra không vẽ kết quả. Status element nay được giữ trong DOM.

Matrix graph thật: trước sửa có 374 `NO_VALID_ROUTE` trong 1,139 node/destination evaluations; sau sửa còn 102 trường hợp thuộc sáu node nằm rõ trong polygon: N002 (B, ~0.71 m), N023 (B, ~0.64 m), N025 (C, ~1.42 m), N027 (B, ~7.77 m), N072 (C, ~1.90 m), N075 (B, ~7.82 m). Không bỏ validation để ép tuyến.

Trường hợp trên ảnh `10.7600286, 106.6820140 → KTH`: API `SUCCESS`, Nearest Node được chọn nhưng `UNVERIFIED`; Nearest Edge bị `INVALID` vì connector giao polygon C. Trường hợp N027 → KTH trả `NO_VALID_ROUTE`; các route/connector cũ được dọn.

## 7. Tệp chính và dữ liệu cần bảo toàn

| Đường dẫn | Vai trò |
|---|---|
| `data/map.html` | Leaflet UI, GPS, hai chế độ, graph debug/editor |
| `data/plot_map.py` | HTTP server và API |
| `scripts/gps_routing.py` | AEQD, projection, virtual node, Dijkstra |
| `scripts/dual_gps_routing.py` | Hai candidate, validation và lựa chọn |
| `scripts/route_between_places.py` | Tuyến địa điểm và CLI |
| `scripts/graph_editor.py` | Patch/revision/backup graph |
| `scripts/build_routing_graph.py`, `prepare_routing_data.py`, `suggest_place_access.py` | Routing data tooling |
| `scripts/test_dual_gps_routing.py`, `scripts/test_graph_editor.py` | Automated tests |
| `data/routing/graph.json`, CSV, GeoJSON | Graph/access/junction metadata |
| `data/ways/`, `data/nodes/` | Dữ liệu hình học nguồn |
| `data/routing/backups/`, `graph_edit_log.jsonl` | Lịch sử khôi phục/audit |
| `data/routing/route_result.geojson` | Kết quả được frontend tham chiếu |

Không xóa các dữ liệu, backup, log, API hay test trên.

## 8. Kết quả xác minh

| Hạng mục | Kết quả |
|---|---|
| Unit tests | 26/26 PASS: 18 dual routing, 8 graph editor |
| Fixture định tuyến | Có kiểm tra cạnh, giữa cạnh, junction, vật cản, ngoài graph, accuracy kém, một/hai/không phương pháp thành công, graph bất biến và Bellman–Ford reference |
| API | Smoke tests trước đó: route evaluate, GPS legacy, between-places trả kết quả; poor accuracy trả HTTP 422 |
| Playwright ảnh GPS | PASS: chờ >6 giây, chọn GPS mô phỏng, API và bảng evaluation chạy; hợp lệ được vẽ, invalid bị loại |
| Lỗi route N027 | PASS: NO_VALID_ROUTE hiển thị, không giữ layer cũ |
| Đổi đích/layer/building route | PASS: clear stale result, toggle độc lập, A→KTH hiển thị 105.24 m |
| Console browser sau sửa status | 0 lỗi JavaScript ở lượt kiểm tra trước |
| GPS thiết bị thật/thực địa | NOT RUN |
| Nét vàng/đỏ trùng sau thay đổi style | PASS: Playwright kiểm tra hai path có cùng geometry; vàng stroke `#eab308` width 10, đỏ `#991b1b` width 4, dash `7 8` |

Sau thay đổi style, đã chạy lại 26 unit tests (đều pass), `node --check` cho inline JavaScript và render test trong Playwright. Test render ép hai tuyến có cùng geometry để xác nhận style của cả hai path cùng tồn tại.

## 9. Các báo cáo đã hợp nhất

Nội dung các báo cáo trước được hợp nhất từ:

- `ROUTING_GRAPH_AUDIT_REPORT.md`
- `ROUTING_FAILURE_FIX_REPORT.md`
- `MOUSE_COORDINATES_GPS_SELECTION_REPORT.md`
- `GRAPH_EDITOR_IMPLEMENTATION_REPORT.md`
- `IMPLEMENTATION_REPORT_GPS_VIRTUAL_NODE.md`

Năm báo cáo rời đã được hợp nhất vào tài liệu này rồi xóa sau khi kiểm tra không có tham chiếu trong mã nguồn. Tất cả file dữ liệu, test, backup, graph edit log và API/runtime vẫn được giữ nguyên.

## 10. Chạy hệ thống và kiểm thử

Từ thư mục CampusNav:

```bash
python3 data/plot_map.py
```

Mở `http://127.0.0.1:8000/map.html`. Chọn chế độ Tòa nhà → Tòa nhà hoặc GPS → Tòa nhà; GPS mô phỏng cần bật chọn trên bản đồ rồi click. GPS thật cần quyền trình duyệt.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

## 11. Giới hạn và việc tiếp theo

- Xác minh access point, cổng, connector dài và obstacle bằng khảo sát thực địa.
- So sánh snapshot graph hiện tại với backup; các báo cáo lịch sử có số liệu graph khác nhau.
- Hiệu chỉnh ngưỡng 50 m trên dữ liệu đo thực tế.
- Bổ sung dữ liệu barrier/footway/one-way/accessibility nếu cần xác minh khả năng đi bộ.
- Kiểm tra GPS thiết bị thật và trực quan hóa tuyến đỏ/vàng trùng nhau sau thay đổi style.
- AEQD cầu được dùng trong implementation ghi nhận; chưa có bằng chứng sai số thực địa cho khuôn viên.

Không tuyên bố tuyến `UNVERIFIED` là an toàn hoặc đã xác nhận đi bộ.
