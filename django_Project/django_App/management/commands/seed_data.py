"""Seed database with sample categories, products, seller, coupons, and reviews."""
import shutil
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django_App.products.models import Category, Product, Review
from django_App.orders.models import Coupon

User = get_user_model()

PRODUCTS_DATA = [
    {
        "title": "Studio Wireless Pro Headphones",
        "category": "Electronics",
        "price": Decimal("149.99"),
        "stock": 25,
        "image": "headphones.jpg",
        "description": "High-fidelity active noise-cancelling wireless headphones with 40-hour battery life and ultra-comfortable memory foam ear cushions.",
    },
    {
        "title": "Minimalist Chronograph Watch",
        "category": "Accessories",
        "price": Decimal("89.00"),
        "stock": 18,
        "image": "watch.jpg",
        "description": "Sleek stainless steel case with genuine Italian leather strap, scratch-resistant sapphire glass, and Japanese quartz movement.",
    },
    {
        "title": "Urban Streetwear Sneakers",
        "category": "Footwear",
        "price": Decimal("119.50"),
        "stock": 20,
        "image": "sneakers.jpg",
        "description": "Breathable knit upper with responsive cushioned sole designed for all-day comfort and street-ready style.",
    },
    {
        "title": "All-Weather Commuter Backpack",
        "category": "Accessories",
        "price": Decimal("65.00"),
        "stock": 15,
        "image": "backpack.jpg",
        "description": "Water-resistant 25L commuter backpack featuring a padded 16-inch laptop sleeve, hidden anti-theft pockets, and ergonomic straps.",
    },
    {
        "title": "Classic Polarized Sunglasses",
        "category": "Accessories",
        "price": Decimal("45.00"),
        "stock": 35,
        "image": "sunglasses.jpg",
        "description": "UV400 protective polarized lenses in a lightweight, durable acetate frame with anti-glare finish.",
    },
    {
        "title": "Vintage Mirrorless Camera",
        "category": "Electronics",
        "price": Decimal("499.00"),
        "stock": 8,
        "image": "camera.jpg",
        "description": "Retro-styled 24.2 MP digital camera with 4K video recording, fast hybrid autofocus, and interchangeable lens mount.",
    },
    {
        "title": "Mechanical Gaming Keyboard",
        "category": "Electronics",
        "price": Decimal("79.99"),
        "stock": 22,
        "image": "keyboard.jpg",
        "description": "Customizable RGB backlit mechanical keyboard with hot-swappable tactile switches and double-shot PBT keycaps.",
    },
    {
        "title": "Nordic Ambient Desk Lamp",
        "category": "Home & Living",
        "price": Decimal("39.99"),
        "stock": 4,  # Low stock demonstration item!
        "image": "lamp.jpg",
        "description": "Scandinavian minimalist adjustable LED desk lamp with touch dimming, warm ambient tones, and USB charging port.",
    },
    {
        "title": "Insulated Thermal Steel Bottle",
        "category": "Home & Living",
        "price": Decimal("24.50"),
        "stock": 45,
        "image": "bottle.jpg",
        "description": "Double-wall vacuum insulated stainless steel water bottle that keeps drinks ice-cold for 24 hours or piping hot for 12 hours.",
    },
    {
        "title": "Waterproof Mountain Explorer Jacket",
        "category": "Fashion & Apparel",
        "price": Decimal("135.00"),
        "stock": 12,
        "image": "jackets.jpg",
        "description": "Breathable, windproof three-layer hardshell jacket with sealed seams and storm hood built for outdoor adventures.",
    },
]


class Command(BaseCommand):
    help = "Seeds categories, products, sellers, coupons, and sample reviews"

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")

        # 1. Update/Ensure Admin User
        admin_user = User.objects.filter(username="admin").first()
        if admin_user:
            admin_user.role = User.Role.ADMIN
            admin_user.status = User.Status.ACTIVE
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"Configured admin user: {admin_user.username} (role=admin)"))
        else:
            admin_user = User.objects.create_superuser("admin", "admin@vendro.com", "password123")
            admin_user.role = User.Role.ADMIN
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin user: admin"))

        # 2. Update/Ensure Seller User
        seller = User.objects.filter(role=User.Role.SELLER).first()
        if not seller:
            seller = User.objects.create_user(
                username="seller",
                email="seller@vendro.com",
                password="password123",
                first_name="Summer",
                last_name="Carter",
                role=User.Role.SELLER,
                status=User.Status.ACTIVE,
                shop_name="Nordic Lifestyle Co.",
            )
            self.stdout.write(self.style.SUCCESS("Created seller: seller (password123)"))
        else:
            seller.status = User.Status.ACTIVE
            if not seller.shop_name:
                seller.shop_name = "Nordic Lifestyle Co."
            seller.save()
            self.stdout.write(self.style.SUCCESS(f"Using seller: {seller.username} ({seller.shop_name})"))

        # 3. Ensure Customer User
        customer = User.objects.filter(role=User.Role.CUSTOMER).first()
        if not customer:
            customer = User.objects.create_user(
                username="customer",
                email="customer@vendro.com",
                password="password123",
                first_name="Alex",
                last_name="Johnson",
                role=User.Role.CUSTOMER,
                status=User.Status.ACTIVE,
            )
            self.stdout.write(self.style.SUCCESS("Created customer: customer (password123)"))

        # 4. Categories
        categories_map = {}
        category_names = ["Electronics", "Accessories", "Footwear", "Fashion & Apparel", "Home & Living"]
        for cat_name in category_names:
            category, _ = Category.objects.get_or_create(
                name=cat_name,
                defaults={"description": f"Curated selection of {cat_name.lower()}."}
            )
            categories_map[cat_name] = category

        self.stdout.write(self.style.SUCCESS(f"Ensured {len(categories_map)} categories."))

        # 5. Media directory for product image uploads
        media_products_dir = settings.MEDIA_ROOT / "products"
        media_products_dir.mkdir(parents=True, exist_ok=True)
        static_img_dir = settings.BASE_DIR / "django_App" / "static" / "images"

        # 6. Products
        created_count = 0
        for p_data in PRODUCTS_DATA:
            img_filename = p_data.get("image")
            img_rel_path = ""
            if img_filename:
                src_path = static_img_dir / img_filename
                dest_path = media_products_dir / img_filename
                if src_path.exists():
                    shutil.copyfile(src_path, dest_path)
                    img_rel_path = f"products/{img_filename}"

            product, created = Product.objects.get_or_create(
                title=p_data["title"],
                defaults={
                    "seller": seller,
                    "category": categories_map[p_data["category"]],
                    "price": p_data["price"],
                    "stock": p_data["stock"],
                    "description": p_data["description"],
                    "image": img_rel_path,
                    "status": Product.Status.ACTIVE,
                }
            )
            if created:
                created_count += 1
            else:
                product.seller = seller
                product.category = categories_map[p_data["category"]]
                product.price = p_data["price"]
                product.stock = p_data["stock"]
                product.description = p_data["description"]
                if img_rel_path:
                    product.image = img_rel_path
                product.status = Product.Status.ACTIVE
                product.save()

        self.stdout.write(self.style.SUCCESS(f"Saved {Product.objects.count()} active products with matching photography."))

        # 7. Coupons
        coupons = [
            {"code": "WELCOME10", "discount_percent": 10, "min_order": Decimal("0.00")},
            {"code": "SUMMER20", "discount_percent": 20, "min_order": Decimal("50.00")},
            {"code": "SAVE30", "discount_percent": 30, "min_order": Decimal("100.00")},
        ]
        for c in coupons:
            Coupon.objects.get_or_create(
                code=c["code"],
                defaults={
                    "discount_percent": c["discount_percent"],
                    "min_order": c["min_order"],
                    "active": True,
                }
            )
        self.stdout.write(self.style.SUCCESS("Created promotional coupons: WELCOME10, SUMMER20, SAVE30"))

        # 8. Sample Reviews
        sample_reviews = [
            ("Studio Wireless Pro Headphones", 5, "Incredible sound quality and battery life. Best headphones I've owned!"),
            ("Minimalist Chronograph Watch", 5, "Gets compliments everywhere I go. Very elegant packaging."),
            ("Urban Streetwear Sneakers", 4, "Extremely comfortable for walking all day. Fits true to size."),
            ("Classic Polarized Sunglasses", 5, "Crisp clarity in bright sunlight. Very sturdy hinges."),
            ("Mechanical Gaming Keyboard", 5, "Satisfying clicks and amazing lighting options. Great build!"),
            ("Nordic Ambient Desk Lamp", 4, "Warm, modern light. Perfect for late night study sessions."),
        ]
        for title, rating, comment in sample_reviews:
            prod = Product.objects.filter(title=title).first()
            if prod and customer:
                Review.objects.get_or_create(
                    product=prod,
                    user=customer,
                    defaults={"rating": rating, "comment": comment}
                )

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
