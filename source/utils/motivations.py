import random

def get_motivation():
    motivations = [
        "Hãy cố gắng thêm một chút nữa — bạn đang tiến bộ từng ngày! 🚀",
        "Mỗi giờ học hôm nay đều giúp bạn giỏi hơn ngày hôm qua. 💪",
        "Cứ kiên trì, thành quả sẽ đến! ✨",
        "Bạn làm được — chỉ cần tiếp tục! 🔥",
        "Học một chút mỗi ngày tạo nên sự khác biệt lớn. 📚",
        "Đừng bỏ cuộc nhé, bạn đang đi đúng hướng! 🌟",
        "Tương lai của bạn cảm ơn bạn vì nỗ lực hôm nay. 🌈",
    ]
    return random.choice(motivations)
