---
title: "Fake static property DateTime.Now() with a DateTime Provider"
date: 2021-05-04T00:00:00+02:00
draft: false
author: "Marcel"
description: "Our code is often time-dependent. We use the date or time to implement logic and make decisions in our code. The behavior of DateTime.Now or DateTime.UtcNow can differ due to the system, timezone and the time change (summer/winter). This means that we have to control this for our tests."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

Our code is often time-dependent. We use the date or time to implement logic and make decisions in our code. The behavior of DateTime.Now or DateTime.UtcNow can differ due to the system, timezone and the time change (summer/winter). This means that we have to control this for our tests.

Take this method for instance:

```csharp
public double ReturnCurrentOffset()
{
    var result = DateTime.Now - DateTime.UtcNow;

    return result.TotalMinutes;
}
```

As you see, this method calculates the current offset with `DateTime.Now` and `DateTime.UtcNow`. Now suppose you want to write unit test for it. We can not control the static properties. The result will be different over the year and the test will fail in the future.

The cleaner way of doing that is to create an interface and a class wrapped around the static datetime properties.

```csharp
public interface IDateTimeProvider
{
    DateTime GetDateTimeNow();

    DateTime GetDateTimeUtcNow();
}
```

```csharp
public class DateTimeProvider : IDateTimeProvider
{
    public DateTime GetDateTimeNow()
    {
        return DateTime.Now;
    }

    public DateTime GetDateTimeUtcNow()
    {
        return DateTime.UtcNow;
    }
}
```

Now we can use the `IDateTimeProvider` in our code example.

```csharp
public class OffsetService
{
    readonly IDateTimeProvider _dateTimeProvider;

    public OffsetService(IDateTimeProvider dateTimeProvider)
    {
        _dateTimeProvider = dateTimeProvider;
    }

    public double ReturnCurrentOffset()
    {
        var now = _dateTimeProvider.GetDateTimeNow();
        var utc = _dateTimeProvider.GetDateTimeUtcNow();

        var result = now - utc;
        return result.TotalMinutes;
    }
}
```

Now you can use your favorite mocking framework and take control over the `IDateTimeProvider`. I'm using [xUnit.net](https://xunit.net/), [FakeItEasy](https://fakeiteasy.github.io/) and [FluentAssertion](https://fluentassertions.com/) in my example.

```csharp
[Fact]
public void OffsetServiceTest()
{
    var fakeDateTimeProvider = A.Fake<IDateTimeProvider>();

    var fakeNow = 3.May(2021).At(18, 30, 22);

    var fakeUtcNow = 3.May(2021).At(16, 30, 22);

    A.CallTo(() => fakeDateTimeProvider.GetDateTimeNow())
        .Returns(fakeNow);
    A.CallTo(() => fakeDateTimeProvider.GetDateTimeUtcNow())
        .Returns(fakeUtcNow);

    var offset = new OffsetService(fakeDateTimeProvider);

    var result = offset.ReturnCurrentOffset();

    result.Should().Be(120);
}
```

It’s testable, clean and I can ensure you that this test is repeatable and it will be green every day.

Happy coding.