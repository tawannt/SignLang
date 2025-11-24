# -*- coding: utf-8 -*-
"""
sign_dict.py
Danh sách 105 ký hiệu ngôn ngữ ký hiệu Việt Nam (VSL)
Lấy từ Giáo trình ngôn ngữ kí hiệu thực hành
Key: index (int)
Value: chuỗi tiếng Việt (str)
"""

SIGN_DICT = {
    # B1. Bảng chữ cái (19)
    # Trang 75
    0: "A", 1: "Ă", 2: "Â", 3: "B", 4: "C", 5: "D", 6: "Đ", 7: "E", 8: "Ê", 9: "G",
    10: "H", 11: "I", 12: "K", 13: "L", 14: "M", 15: "N", 16: "O", 17: "Ô", 18: "Ơ",
    19: "P", 20: "Q", 21: "R", 22: "S", 23: "T", 24: "U", 25: "Ư", 26: "V", 27: "X",
    28: "Y", 

    # B2. Số & Thời gian (23)
    # Trang 76
    29: "Số 1", 30: "Số 2", 31: "Số 3", 32: "Số 4", 33: "Số 5", 
    34: "Số 6", 35: "Số 7", 36: "Số 8", 37: "Số 9", 38: "Số 10",
    # Trang 130
    39: "Thời gian", 40: "Hỏi giờ", 41: "Ngày", 42: "Tháng", 43: "Năm",
    44: "Hôm nay", 45: "Hôm qua", 46: "Buổi sáng",
    47: "Buổi trưa", 48: "Buổi chiều", 49: "Buổi tối", 50: "Đêm",

    # B3. Làm quen & Cảm xúc (15)
    # Trang 94
    51: "Tôi", 52: "Chào", 53: "Xin lỗi", 54: "Xin phép",
    55: "Vui", 56: "Buồn", 57: "Mệt", 58: "Khỏe", 59: "Yếu",
    60: "Bạn", 61: "Tên là gì", 62: "Tuổi", 63: "Thế nào",
    64: "Bao nhiêu", 65: "Ở đâu", 66: "Làm gì",

    # B4. Hoạt động hằng ngày (13)
    # Trang 83
    67: "Đi", 68: "Đứng", 69: "Ngồi", 70: "Nằm", 71: "Chạy",
    72: "Nhảy", 73: "Ngủ", 74: "Đi vệ sinh", 75: "Ăn", 76: "Uống",
    77: "Tắm", 78: "Khóc", 79: "Cười",

    # B5. Gia đình (14)
    # Trang 103
    80: "Gia đình", 81: "Ông", 82: "Bà", 83: "Bố", 84: "Mẹ",
    85: "Em trai", 86: "Em gái", 87: "Con trai", 88: "Con gái",
    89: "Vợ", 90: "Chồng", 91: "Anh trai", 92: "Chị gái", 93: "Em út",
    94: "Yêu",

    # B6. Địa điểm & Nghề nghiệp (7)
    # Trang 120
    95: "Cô giáo", 96: "Công nhân", 97: "Nông dân",
    98: "Bác sĩ", 99: "Y tá", 100: "Công an", 101: "Bộ đội",

    102: "UNKNOWN"
}

SIGN_DICT_NO_ACCENT = {
    # B1. Bang chu cai (19)
    0: "A", 1: "A1", 2: "A2", 3: "B", 4: "C", 5: "D", 6: "D1", 7: "E", 8: "E1", 9: "G",
    10: "H", 11: "I", 12: "K", 13: "L", 14: "M", 15: "N", 16: "O", 17: "O1", 18: "O2",
    19: "P", 20: "Q", 21: "R", 22: "S", 23: "T", 24: "U", 25: "U1", 26: "V", 27: "X",
    28: "Y",

    # B2. So & Thoi gian (23)
    29: "So 1", 30: "So 2", 31: "So 3", 32: "So 4", 33: "So 5",
    34: "So 6", 35: "So 7", 36: "So 8", 37: "So 9", 38: "So 10",
    39: "Thoi gian", 40: "Hoi gio", 41: "Ngay", 42: "Thang", 43: "Nam",
    44: "Hom nay", 45: "Hom qua", 46: "Buoi sang",
    47: "Buoi trua", 48: "Buoi chieu", 49: "Buoi toi", 50: "Dem",

    # B3. Lam quen & Cam xuc (15)
    51: "Toi", 52: "Chao", 53: "Xin loi", 54: "Xin phep",
    55: "Vui", 56: "Buon", 57: "Met", 58: "Khoe", 59: "Yeu",
    60: "Ban", 61: "Ten la gi", 62: "Tuoi", 63: "The nao",
    64: "Bao nhieu", 65: "O dau", 66: "Lam gi",

    # B4. Hoat dong hang ngay (13)
    67: "Di", 68: "Dung", 69: "Ngoi", 70: "Nam", 71: "Chay",
    72: "Nhay", 73: "Ngu", 74: "Di ve sinh", 75: "An", 76: "Uong",
    77: "Tam", 78: "Khoc", 79: "Cuoi",

    # B5. Gia dinh (14)
    80: "Gia dinh", 81: "Ong", 82: "Ba", 83: "Bo", 84: "Me",
    85: "Em trai", 86: "Em gai", 87: "Con trai", 88: "Con gai",
    89: "Vo", 90: "Chong", 91: "Anh trai", 92: "Chi gai", 93: "Em ut",
    94: "Yeu",

    # B6. Dia diem & Nghe nghiep (7)
    95: "Co giao", 96: "Cong nhan", 97: "Nong dan",
    98: "Bac si", 99: "Y ta", 100: "Cong an", 101: "Bo doi",

    102: "UNKNOWN"
}


# Ánh xạ ngược (chuỗi -> index)
SIGN_TO_INDEX = {v: k for k, v in SIGN_DICT.items()}
